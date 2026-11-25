#!/usr/bin/env python3
"""보고서 명령: 조회용 SQLite 데이터베이스에서 검증 공백 보고서(HTML 파일 하나)를 만든다.

사용자가 실행한다. 데이터베이스가 없거나 오래되었으면 오류로 종료한다.
데이터 폴더는 --data-dir 인자나 환경 변수 FTM_DATA_DIR로 전달받으며, 보고서는 그 폴더의 build/report.html에 만든다.
보고서의 수치는 조회 스크립트와 같은 집계 뷰에서 읽는다.
보고서는 '검증 공백'과 '관계 지도'의 두 화면으로 구성되며, 두 화면은 틀(template.html) 안에 있다.
TC의 분류(owner, platform)별 수치도 분류별 집계 뷰에서 읽어 함께 넣으며, 화면에서 분류를 고르면 그 수치로 바꾸어 보인다.

이 폴더(report/)는 보고서에만 쓰이는 파일을 담으며, 스킬의 공용 모듈(scripts/common.py)에만 의존한다.
"""

import sys

sys.dont_write_bytecode = True

import argparse
import datetime
import json
import os
import sqlite3
from pathlib import Path

REPORT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPORT_DIR.parent / "scripts"))

import common  # noqa: E402

TEMPLATE_PATH = REPORT_DIR / "template.html"
DATA_MARK = "/*__DATA__*/"
REPORT_NAME = "report.html"
# TC의 분류 항목. 항목마다 값 목록 뷰(v_tc_<항목>)와 분류별 집계 뷰(v_*_by_<항목>)가 정의 파일에 있다.
CLASS_AXES = ("owner", "platform")

# 틀은 본문만 담는다. 파일 하나로 열리도록 문서의 머리를 붙인다.
HTML_HEAD = (
    '<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    "<style>body{margin:0}[hidden]{display:none!important}</style>\n</head>\n<body>\n"
)
HTML_TAIL = "\n</body>\n</html>\n"


def report_path(data_dir):
    return common.db_path(data_dir).with_name(REPORT_NAME)


def collect_classes(conn):
    """TC의 분류 값마다, 그 값인 TC만으로 구한 수치를 분류별 집계 뷰에서 읽는다."""
    classes = []
    for axis in CLASS_AXES:
        for (value,) in conn.execute(f"SELECT {axis} FROM v_tc_{axis}").fetchall():
            features = {
                row[0]: {"tc_count": row[1], "uncovered_leaf_count": row[2], "uncovered_scenario_count": row[3]}
                for row in conn.execute(
                    "SELECT st.feature_id, st.tc_count, st.uncovered_leaf_count, c.uncovered_scenario_count "
                    f"FROM v_subtree_tc_count_by_{axis} st "
                    f"LEFT JOIN v_feature_tc_count_by_{axis} c ON c.{axis} = st.{axis} AND c.feature_id = st.feature_id "
                    f"WHERE st.{axis} = ?",
                    (value,),
                )
            }
            scenarios = dict(conn.execute(
                f"SELECT scenario_id, tc_count FROM v_scenario_tc_count_by_{axis} WHERE {axis} = ?", (value,)
            ))
            names = (
                "leaf_count", "uncovered_leaf_count", "scenario_count", "uncovered_scenario_count",
                "tc_count", "unlinked_tc_count",
            )
            totals = conn.execute(
                f"SELECT (SELECT COUNT(*) FROM v_feature_tc_count_by_{axis} WHERE {axis} = :v), "
                f"       (SELECT COUNT(*) FROM v_feature_tc_count_by_{axis} WHERE {axis} = :v AND tc_count = 0), "
                f"       (SELECT COUNT(*) FROM v_scenario_tc_count_by_{axis} WHERE {axis} = :v), "
                f"       (SELECT COUNT(*) FROM v_scenario_tc_count_by_{axis} WHERE {axis} = :v AND tc_count = 0), "
                f"       (SELECT COUNT(*) FROM tc WHERE {axis} = :v), "
                f"       (SELECT COUNT(*) FROM v_unlinked_tc WHERE {axis} = :v)",
                {"v": value},
            ).fetchone()
            classes.append({
                "axis": axis, "value": value, "totals": dict(zip(names, totals)),
                "features": features, "scenarios": scenarios,
            })
    return classes


def collect(conn, info, data_dir):
    """집계 뷰에서 보고서에 넣을 데이터를 읽는다."""

    def rows(sql):
        cursor = conn.execute(sql)
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row)) for row in cursor]

    by_parent = {}
    for row in rows(
        "SELECT f.id, f.name, f.path, f.parent_id, f.description, f.ims_ref, "
        "       (l.id IS NOT NULL) AS is_leaf, st.leaf_count, st.uncovered_leaf_count, st.tc_count, "
        "       c.scenario_count, c.uncovered_scenario_count "
        "FROM feature f "
        "JOIN v_subtree_tc_count st ON st.feature_id = f.id "
        "LEFT JOIN v_leaf_feature l ON l.id = f.id "
        "LEFT JOIN v_feature_tc_count c ON c.feature_id = f.id "
        "ORDER BY f.rowid"
    ):
        row["is_leaf"] = bool(row["is_leaf"])
        by_parent.setdefault(row["parent_id"], []).append(row)

    # 원본에 적힌 순서를 유지하면서, 하위 기능이 상위 기능 바로 아래에 오도록 늘어놓는다.
    features = []
    stack = [(None, 0)]
    pending = {parent: list(children) for parent, children in by_parent.items()}
    while stack:
        parent, depth = stack[-1]
        children = pending.get(parent)
        if not children:
            stack.pop()
            continue
        row = children.pop(0)
        row["depth"] = depth
        features.append(row)
        stack.append((row["id"], depth + 1))

    links = {}
    for scenario_id, tc_id in conn.execute("SELECT scenario_id, tc_id FROM scenario_tc ORDER BY tc_id"):
        links.setdefault(scenario_id, []).append(tc_id)
    scenarios = rows(
        "SELECT s.id, s.feature_id, s.stimulus, s.environment, s.response, s.response_measure, c.tc_count "
        "FROM scenario s JOIN v_scenario_tc_count c ON c.scenario_id = s.id ORDER BY s.rowid"
    )
    for scenario in scenarios:
        scenario["tc_ids"] = links.get(scenario["id"], [])

    # 여러 기능을 함께 검증하는 TC만 담는다.
    tc_features = {}
    for tc_id, feature_id in conn.execute(
        "SELECT tc_id, feature_id FROM v_feature_tc "
        "WHERE tc_id IN (SELECT tc_id FROM v_feature_tc GROUP BY tc_id HAVING COUNT(*) > 1) "
        "ORDER BY tc_id, feature_id"
    ):
        tc_features.setdefault(tc_id, []).append(feature_id)

    totals = rows(
        "SELECT (SELECT COUNT(*) FROM v_feature_tc_count) AS leaf_count, "
        "       (SELECT COUNT(*) FROM v_feature_tc_count WHERE tc_count = 0) AS uncovered_leaf_count, "
        "       (SELECT COUNT(*) FROM v_scenario_tc_count) AS scenario_count, "
        "       (SELECT COUNT(*) FROM v_scenario_tc_count WHERE tc_count = 0) AS uncovered_scenario_count, "
        "       (SELECT COUNT(*) FROM tc) AS tc_count, "
        "       (SELECT COUNT(*) FROM v_unlinked_tc) AS unlinked_tc_count"
    )[0]

    return {
        "meta": {
            "data_dir": str(data_dir),
            "built_at": info.get("built_at", ""),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        },
        "totals": totals,
        "features": features,
        "scenarios": scenarios,
        "tcs": rows("SELECT id, suite, name, source_file, owner, platform FROM tc ORDER BY id"),
        "classes": collect_classes(conn),
        "tc_features": tc_features,
        "unlinked_tc_ids": [row[0] for row in conn.execute("SELECT id FROM v_unlinked_tc ORDER BY id")],
    }


def render(data):
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if template.count(DATA_MARK) != 1:
        raise common.FtmError(f"보고서의 틀에 데이터를 넣을 자리({DATA_MARK})가 하나가 아니다: {TEMPLATE_PATH}")
    # 데이터 안의 문자열이 script 요소를 닫지 못하게 한다.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return HTML_HEAD + template.replace(DATA_MARK, payload) + HTML_TAIL


def write_atomically(path, text):
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        try:
            os.replace(tmp, path)
        except OSError as e:
            raise common.FtmError(f"보고서 파일을 교체할 수 없다: {path}\n기존 파일은 그대로 두었다. ({e})")
    finally:
        if tmp.exists():
            tmp.unlink()


def main():
    common.configure_output()
    parser = argparse.ArgumentParser(description="Feature-Test Map 보고서 명령")
    parser.add_argument("--data-dir", help="데이터 폴더의 경로. 없으면 환경 변수 FTM_DATA_DIR을 쓴다.")
    args = parser.parse_args()

    try:
        data_dir = common.resolve_data_dir(args.data_dir)
        conn, info = common.open_checked(data_dir)
        try:
            data = collect(conn, info, data_dir)
        finally:
            conn.close()
        target = report_path(data_dir)
        write_atomically(target, render(data))
    except common.FtmError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    except sqlite3.Error as e:
        print(f"오류: 데이터베이스를 읽는 중에 SQLite 오류가 발생하였다. ({e})", file=sys.stderr)
        return 1

    totals = data["totals"]
    print("보고서를 만들었다. 브라우저로 연다.")
    print(f"보고서: {target}")
    print(f"데이터베이스 생성 시각: {data['meta']['built_at']}")
    print(
        f"검증되지 않은 기능 {totals['uncovered_leaf_count']}개(검증 대상 {totals['leaf_count']}개), "
        f"TC가 없는 인스턴스 시나리오 {totals['uncovered_scenario_count']}개(전체 {totals['scenario_count']}개), "
        f"연결되지 않은 TC {totals['unlinked_tc_count']}개(전체 {totals['tc_count']}개)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
