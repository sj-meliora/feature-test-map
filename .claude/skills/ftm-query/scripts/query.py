#!/usr/bin/env python3
"""조회 스크립트: 조회용 SQLite 데이터베이스를 읽기 전용으로 조회한다.

명령:
  schema          데이터 폴더의 경로, 테이블과 뷰의 정의, 테이블별 레코드 수, 생성 시각을 출력한다.
  sql "<SELECT>"  SQL 한 문장을 실행하고 결과를 표로 출력한다.

어떤 파일도 쓰지 않는다. 데이터베이스가 없거나 오래되었으면 오류로 종료한다.
데이터 폴더는 환경 변수 FTM_DATA_DIR로 전달받는다.
"""

import sys

sys.dont_write_bytecode = True

import argparse
import sqlite3

import common

ROW_LIMIT = 200

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


def _authorizer(action, arg1, arg2, db_name, source):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def _stale(reason, data_dir, extra=None):
    lines = [
        reason,
        f"데이터 폴더: {data_dir}",
        f"데이터베이스: {common.db_path(data_dir)}",
        "아래의 명령을 실행하여 데이터베이스를 만든다.",
    ]
    if extra:
        lines.append(extra)
    lines += ["", f"  {common.build_command_line(data_dir)}"]
    return common.FtmError("\n".join(lines))


def open_checked(data_dir):
    """최신성을 검사한 뒤, 읽기 전용으로 연 연결과 생성 정보를 돌려준다."""
    source_hash = common.source_hash(data_dir)
    schema_hash = common.schema_hash()
    path = common.db_path(data_dir)
    if not path.is_file():
        raise _stale("데이터베이스가 아직 만들어지지 않았다.", data_dir)

    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
        try:
            info = dict(conn.execute("SELECT key, value FROM build_info"))
        except sqlite3.Error:
            raise _stale("데이터베이스에서 생성 정보를 읽을 수 없다.", data_dir)

        reasons = []
        extra = None
        if info.get("source_hash") != source_hash:
            reasons.append("원본이 데이터베이스를 만든 뒤에 바뀌었다.")
        if info.get("schema_hash") != schema_hash:
            reasons.append("데이터베이스가 이 스킬의 정의와 다른 정의로 만들어졌다.")
            extra = "저장소에서 정의를 고쳤다면 플러그인을 먼저 다시 설치한다."
        if reasons:
            raise _stale(" ".join(reasons), data_dir, extra)

        conn.set_authorizer(_authorizer)
    except BaseException:
        conn.close()
        raise
    return conn, info


def _cell(value):
    if value is None:
        return "NULL"
    text = value.decode("utf-8", "replace") if isinstance(value, bytes) else str(value)
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def print_table(columns, rows):
    print("| " + " | ".join(_cell(c) for c in columns) + " |")
    print("|" + "---|" * len(columns))
    for row in rows:
        print("| " + " | ".join(_cell(v) for v in row) + " |")


def cmd_schema(conn, info, data_dir):
    objects = conn.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
        "ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, name"
    ).fetchall()
    print(f"데이터 폴더: {data_dir}")
    print(f"기능 원본: {data_dir / common.FEATURES_FILE}")
    print(f"데이터베이스: {common.db_path(data_dir)}")
    print(f"생성 시각: {info.get('built_at', '')}")
    print()
    print("테이블별 레코드 수:")
    for kind, name, _ in objects:
        if kind == "table" and name != "build_info":
            count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            print(f"- {name}: {count}")
    print()
    print("테이블과 뷰의 정의:")
    for _, _, sql in objects:
        print()
        print(sql.strip() + ";")
    return 0


def cmd_sql(conn, statement):
    try:
        cursor = conn.execute(statement)
    except (sqlite3.Error, sqlite3.Warning) as e:
        message = str(e)
        if any(word in message for word in ("not authorized", "authorization denied", "readonly", "read-only")):
            message += " (조회 스크립트는 읽기 전용이며 SELECT 문만 실행한다.)"
        print(f"오류: SQL을 실행할 수 없다: {message}", file=sys.stderr)
        return 1
    if cursor.description is None:
        print("오류: 결과를 돌려주는 SELECT 문 한 문장만 실행할 수 있다.", file=sys.stderr)
        return 1
    columns = [d[0] for d in cursor.description]
    try:
        rows = cursor.fetchmany(ROW_LIMIT + 1)
    except sqlite3.Error as e:
        print(f"오류: SQL을 실행할 수 없다: {e}", file=sys.stderr)
        return 1
    truncated = len(rows) > ROW_LIMIT
    rows = rows[:ROW_LIMIT]
    print_table(columns, rows)
    print()
    if truncated:
        print(f"(결과가 {ROW_LIMIT}행을 넘어 처음 {ROW_LIMIT}행만 출력하였다. 이 출력의 행을 세지 않는다. 개수는 COUNT로 구한다.)")
    else:
        print(f"({len(rows)}행)")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Feature-Test Map 조회 스크립트 (읽기 전용)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("schema", help="데이터 폴더의 경로와 테이블, 뷰의 정의를 출력한다")
    p_sql = sub.add_parser("sql", help="SELECT 문 한 문장을 실행한다")
    p_sql.add_argument("statement", help="실행할 SELECT 문")
    args = parser.parse_args()

    try:
        data_dir = common.resolve_data_dir()
        conn, info = open_checked(data_dir)
    except common.FtmError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2
    try:
        if args.command == "schema":
            return cmd_schema(conn, info, data_dir)
        return cmd_sql(conn, args.statement)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
