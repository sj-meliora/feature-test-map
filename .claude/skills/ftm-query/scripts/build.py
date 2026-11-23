#!/usr/bin/env python3
"""변환 명령: 원본(features.yaml)에서 조회용 SQLite 데이터베이스를 만든다.

사용자가 실행한다. 에이전트와 조회 스크립트는 이 명령을 실행하지 않는다.
데이터 폴더는 환경 변수 FTM_DATA_DIR로 전달받는다.
"""

import sys

sys.dont_write_bytecode = True

import datetime
import os
import sqlite3

import common

FIELDS = ("id", "name", "path", "parent_id", "description", "ims_ref")
PATH_SEP = " > "


def load_yaml_module():
    """설치된 PyYAML이 있으면 그것을 쓰고, 없으면 스킬에 포함한 사본을 쓴다."""
    try:
        import yaml
    except ImportError:
        sys.modules.pop("yaml", None)
        sys.path.insert(0, str(common.VENDOR_DIR))
        import yaml
    return yaml


def read_source(path):
    """원본을 읽어 (값, 오류 목록)을 돌려준다. 원본을 해석하는 부분은 이 함수에 모은다."""
    yaml = load_yaml_module()

    class Loader(yaml.SafeLoader):
        """같은 레코드 안에 키가 두 번 나오면 오류로 처리하는 로더."""

    def construct_mapping(loader, node):
        seen = set()
        for key_node, _ in node.value:
            key = loader.construct_object(key_node, deep=True)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"키 {key!r}가 한 레코드 안에 두 번 나온다", key_node.start_mark
                )
            seen.add(key)
        return loader.construct_mapping(node, deep=True)

    Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping)

    try:
        with open(path, encoding="utf-8") as f:
            return yaml.load(f, Loader=Loader), []
    except yaml.YAMLError as e:
        return None, [f"YAML을 해석할 수 없다: {' '.join(str(e).split())}"]
    except UnicodeDecodeError as e:
        return None, [f"파일이 UTF-8이 아니다: {e}"]


def validate(data):
    """검증 규칙(design/dp4.md)으로 원본을 검사하여 오류를 모두 모은다."""
    errors = []
    if data is None:
        return [], errors
    if not isinstance(data, list):
        return [], ["파일의 최상위는 레코드의 목록이어야 한다."]

    def label(index, rec):
        rid = rec.get("id") if isinstance(rec, dict) else None
        if isinstance(rid, str) and rid.strip():
            return f"[{rid}]"
        return f"[{index + 1}번째 레코드]"

    records = []
    for index, rec in enumerate(data):
        tag = label(index, rec)
        if not isinstance(rec, dict):
            errors.append(f"{tag} 레코드가 '키: 값'의 묶음이 아니다.")
            continue
        ok = True
        for key in FIELDS:
            if key not in rec:
                errors.append(f"{tag} 키 {key}가 없다.")
                ok = False
        for key in rec:
            if key not in FIELDS:
                errors.append(f"{tag} 정의되지 않은 키 {key!r}가 있다.")
                ok = False
        for key in FIELDS:
            if key not in rec:
                continue
            value = rec[key]
            if key == "parent_id" and value is None:
                continue
            if not isinstance(value, str):
                shown = "null" if value is None else repr(value)
                errors.append(
                    f"{tag} {key}의 값 {shown}은 문자열이 아니다({type(value).__name__}). "
                    "YAML은 따옴표가 없는 값을 다른 자료형으로 해석할 수 있으므로, 값을 따옴표로 감싼다."
                )
                ok = False
            elif not value.strip():
                errors.append(f"{tag} {key}의 값이 비어 있다.")
                ok = False
        if ok:
            records.append(rec)

    by_id = {}
    for rec in records:
        if rec["id"] in by_id:
            errors.append(f"[{rec['id']}] id가 중복된다.")
        else:
            by_id[rec["id"]] = rec
    if len(by_id) != len(records):
        records = list(by_id.values())

    unresolved = set()
    for rec in records:
        parent = rec["parent_id"]
        if parent is not None and parent not in by_id:
            errors.append(f"[{rec['id']}] parent_id가 가리키는 기능 {parent!r}가 없다.")
            unresolved.add(rec["id"])

    for rec in records:
        seen = {rec["id"]}
        cur = rec["parent_id"]
        while cur is not None and cur in by_id:
            if cur == rec["id"]:
                errors.append(f"[{rec['id']}] 부모를 따라 올라가면 자신으로 돌아온다(순환).")
                unresolved.add(rec["id"])
                break
            if cur in seen:
                break
            seen.add(cur)
            cur = by_id[cur]["parent_id"]

    for rec in records:
        if rec["id"] in unresolved:
            continue
        parent = rec["parent_id"]
        expected = rec["name"] if parent is None else by_id[parent]["path"] + PATH_SEP + rec["name"]
        if rec["path"] != expected:
            errors.append(f"[{rec['id']}] path가 {rec['path']!r}이지만, 부모의 path와 name으로 구한 값은 {expected!r}이다.")

    return records, errors


def build_database(records, data_dir, source_hash, schema_hash):
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
            conn.executemany(
                "INSERT INTO feature (id, name, path, parent_id, description, ims_ref) VALUES (?, ?, ?, ?, ?, ?)",
                [tuple(rec[key] for key in FIELDS) for rec in records],
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


def main():
    try:
        data_dir = common.resolve_data_dir()
        source_hash = common.source_hash(data_dir)
        schema_hash = common.schema_hash()
        source = data_dir / common.FEATURES_FILE

        data, errors = read_source(source)
        records = []
        if not errors:
            records, errors = validate(data)
        if errors:
            print(f"오류: {source}에서 오류 {len(errors)}개를 발견하였다. 데이터베이스를 만들지 않았다.", file=sys.stderr)
            for message in errors:
                print(f"- {message}", file=sys.stderr)
            return 1

        target, built_at = build_database(records, data_dir, source_hash, schema_hash)
    except common.FtmError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    except sqlite3.Error as e:
        print(f"오류: 데이터베이스를 만드는 중에 SQLite 오류가 발생하였다. 기존 파일은 그대로 두었다. ({e})", file=sys.stderr)
        return 1

    print("데이터베이스를 만들었다.")
    print(f"데이터 폴더: {data_dir}")
    print(f"데이터베이스: {target}")
    print(f"기능 레코드: {len(records)}개")
    print(f"생성 시각: {built_at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
