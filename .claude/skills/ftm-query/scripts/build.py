#!/usr/bin/env python3
"""변환 명령: 원본 네 파일에서 조회용 SQLite 데이터베이스를 만든다.

사용자가 실행한다. 에이전트와 조회 스크립트는 이 명령을 실행하지 않는다.
데이터 폴더는 --data-dir 인자나 환경 변수 FTM_DATA_DIR로 전달받는다. 인자가 있으면 인자가 앞선다.

  build.py [--data-dir <폴더>]       네 원본을 검사하고 데이터베이스를 만든다.
  build.py --check-features <파일>   기능 원본 하나만 검사한다. 데이터베이스를 만들지 않는다.
"""

import sys

sys.dont_write_bytecode = True

import argparse
import datetime
import os
import sqlite3

import common
from ftm_core.sources import (
    FEATURES_FILE,
    RELATIONS_FILE,
    SCENARIOS_FILE,
    TABLE_FIELDS,
    TCS_FILE,
    read_jsonl,
    read_yaml,
    validate_features,
    validate_leaf_coverage,
    validate_relations,
    validate_scenarios,
    validate_tcs,
)

# 값의 목록을 정의 파일의 뷰에서 읽는 TC의 분류 항목. (항목, 값 목록 뷰)
TC_CLASS_VIEWS = (("owner", "v_tc_owner"), ("platform", "v_tc_platform"))


def tc_class_values():
    """owner와 platform에 허용하는 값을 정의 파일의 값 목록 뷰에서 읽는다. 값의 목록은 정의 파일에만 둔다."""
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(common.SCHEMA_PATH.read_text(encoding="utf-8"))
        return {
            key: [row[0] for row in conn.execute(f"SELECT {key} FROM {view}")]
            for key, view in TC_CLASS_VIEWS
        }
    finally:
        conn.close()


def load_sources(data_dir):
    """네 원본을 읽고 검사한다. (테이블별 레코드, [(파일 이름, 오류)])를 돌려준다."""
    errors = []

    def step(name, read, validate):
        """원본 하나를 읽고 검사한다. 오류가 있으면 None을 돌려주어, 이 원본을 참조하는 규칙을 건너뛰게 한다.

        YAML은 해석에 실패하면 레코드를 얻을 수 없으므로 검사를 건너뛴다. JSONL은 해석할 수 없는 줄이
        있어도 나머지 줄을 검사하여, 발견한 오류를 한 번에 모두 보고한다.
        """
        data, found = read(data_dir / name)
        records = []
        if not found or read is read_jsonl:
            records, more = validate(data)
            found = found + more
        errors.extend((name, message) for message in found)
        return None if found else records

    features = step(FEATURES_FILE, read_yaml, validate_features)
    scenarios = step(SCENARIOS_FILE, read_yaml, lambda data: validate_scenarios(data, features))
    if features is not None and scenarios is not None:
        errors.extend((SCENARIOS_FILE, message) for message in validate_leaf_coverage(features, scenarios))
    tcs = step(TCS_FILE, read_jsonl, lambda rows: validate_tcs(rows, tc_class_values()))
    relations = step(RELATIONS_FILE, read_jsonl, lambda rows: validate_relations(rows, scenarios, tcs))

    tables = {"feature": features, "scenario": scenarios, "tc": tcs, "scenario_tc": relations}
    return tables, errors


# ---------------------------------------------------------------------------
# 데이터베이스 만들기
# ---------------------------------------------------------------------------

def build_database(tables, data_dir, source_hash, schema_hash):
    """임시 파일에 데이터베이스 전체를 새로 만든 뒤 최종 경로로 원자적으로 옮긴다."""
    target = common.db_path(data_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp-{os.getpid()}")
    if tmp.exists():
        tmp.unlink()
    built_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    try:
        conn = sqlite3.connect(str(tmp), isolation_level=None)
        try:
            conn.executescript(common.SCHEMA_PATH.read_text(encoding="utf-8"))
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("BEGIN")
            for table, fields in TABLE_FIELDS:
                conn.executemany(
                    f"INSERT INTO {table} ({', '.join(fields)}) VALUES ({', '.join('?' * len(fields))})",
                    [tuple(rec[key] for key in fields) for rec in tables[table]],
                )
            conn.executemany(
                "INSERT INTO build_info (key, value) VALUES (?, ?)",
                [("source_hash", source_hash), ("schema_hash", schema_hash), ("built_at", built_at)],
            )
            conn.execute("COMMIT")
        finally:
            conn.close()
        try:
            os.replace(tmp, target)
        except OSError as e:
            raise common.FtmError(
                f"데이터베이스 파일을 교체할 수 없다: {target}\n"
                f"다른 프로그램이 파일을 열고 있는지 확인한다. 기존 파일은 그대로 두었다. ({e})"
            )
    finally:
        if tmp.exists():
            tmp.unlink()
    return target, built_at


def check_features(path):
    """기능 원본 하나만 검사한다. 다른 원본이 아직 없을 때 쓴다."""
    if not os.path.isfile(path):
        print(f"오류: 파일이 없다: {path}", file=sys.stderr)
        return 2
    data, errors = read_yaml(path)
    records = []
    if not errors:
        records, errors = validate_features(data)
    if errors:
        print(f"오류: {path}에서 오류 {len(errors)}개를 발견하였다.", file=sys.stderr)
        for message in errors:
            print(f"- {message}", file=sys.stderr)
        return 1
    parents = {rec["parent_id"] for rec in records if rec["parent_id"] is not None}
    leaves = sum(1 for rec in records if rec["id"] not in parents)
    print(f"기능 원본에서 오류를 발견하지 못하였다: {path}")
    print(f"기능 레코드: {len(records)}개 (묶음 {len(records) - leaves}개, 검증 대상 {leaves}개)")
    print("인스턴스 시나리오, TC, 시나리오-TC 관계와 맞는지는 검사하지 않았다.")
    return 0


def main():
    common.configure_output()
    parser = argparse.ArgumentParser(description="Feature-Test Map 변환 명령")
    parser.add_argument("--data-dir", help="데이터 폴더의 경로. 없으면 환경 변수 FTM_DATA_DIR을 쓴다.")
    parser.add_argument("--check-features", metavar="FILE", help="기능 원본 하나만 검사하고 데이터베이스를 만들지 않는다.")
    args = parser.parse_args()
    if args.check_features:
        return check_features(args.check_features)

    try:
        data_dir = common.resolve_data_dir(args.data_dir)
        source_hash = common.source_hash(data_dir)
        schema_hash = common.schema_hash()

        tables, errors = load_sources(data_dir)
        if errors:
            print(
                f"오류: {data_dir}의 원본에서 오류 {len(errors)}개를 발견하였다. 데이터베이스를 만들지 않았다.",
                file=sys.stderr,
            )
            for name, message in errors:
                print(f"- {name}: {message}", file=sys.stderr)
            return 1

        target, built_at = build_database(tables, data_dir, source_hash, schema_hash)
    except common.FtmError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    except sqlite3.Error as e:
        print(f"오류: 데이터베이스를 만드는 중에 SQLite 오류가 발생하였다. 기존 파일은 그대로 두었다. ({e})", file=sys.stderr)
        return 1

    print("데이터베이스를 만들었다.")
    print(f"데이터 폴더: {data_dir}")
    print(f"데이터베이스: {target}")
    print(
        f"레코드: 기능 {len(tables['feature'])}개, 인스턴스 시나리오 {len(tables['scenario'])}개, "
        f"TC {len(tables['tc'])}개, 시나리오-TC 관계 {len(tables['scenario_tc'])}개"
    )
    print(f"생성 시각: {built_at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
