"""변환 명령과 조회 스크립트가 함께 쓰는 부분: 경로 해석, 해시 계산, 실행 줄."""

import hashlib
import os
import shlex
import sqlite3
import sys
from pathlib import Path

ENV_VAR = "FTM_DATA_DIR"

# 스크립트는 자신이 놓인 위치를 기준으로 같은 사본의 파일을 찾는다.
SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = SKILL_DIR / "schema.sql"
BUILD_SCRIPT = SKILL_DIR / "scripts" / "build.py"
VENDOR_DIR = SKILL_DIR / "vendor"

FEATURES_FILE = "features.yaml"
SCENARIOS_FILE = "scenarios.yaml"
TCS_FILE = "tcs.jsonl"
RELATIONS_FILE = "scenario_tc.jsonl"
# 원본 파일. 변환에는 네 파일이 모두 있어야 하며, 해시는 네 파일의 내용으로 계산한다.
SOURCE_FILES = (FEATURES_FILE, SCENARIOS_FILE, TCS_FILE, RELATIONS_FILE)


class FtmError(Exception):
    """사용자에게 메시지를 보이고 종료해야 하는 오류."""


def resolve_data_dir():
    """환경 변수에서 데이터 폴더의 절대 경로를 구한다. 기본 경로를 추측하지 않는다."""
    value = os.environ.get(ENV_VAR, "").strip()
    if not value:
        raise FtmError(
            f"환경 변수 {ENV_VAR}이 설정되지 않았다.\n"
            f"데이터 폴더(원본 파일이 있는 폴더)의 경로를 {ENV_VAR}에 설정한 뒤 다시 실행한다."
        )
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise FtmError(
            f"{ENV_VAR}이 가리키는 폴더가 없다: {path}\n"
            f"데이터 폴더(원본 파일이 있는 폴더)의 경로를 {ENV_VAR}에 설정한 뒤 다시 실행한다."
        )
    return path


def db_path(data_dir):
    return data_dir / "build" / "ftm.db"


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def source_hash(data_dir):
    """원본 파일 내용의 해시. 원본 파일이 없으면 오류다."""
    h = hashlib.sha256()
    for name in SOURCE_FILES:
        path = data_dir / name
        if not path.is_file():
            raise FtmError(
                f"원본 파일이 없다: {path}\n데이터 폴더: {data_dir}\n"
                f"데이터 폴더에는 원본 파일 {', '.join(SOURCE_FILES)}이 모두 있어야 한다."
            )
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def schema_hash():
    """같은 사본에 있는 정의 파일 내용의 해시."""
    return _sha256(SCHEMA_PATH.read_bytes())


def build_command_line(data_dir):
    """같은 사본의 변환 명령을 실행하는 줄. 환경 변수의 값을 함께 지정한다."""
    return (
        f"{ENV_VAR}={shlex.quote(str(data_dir))} "
        f"{shlex.quote(sys.executable or 'python3')} {shlex.quote(str(BUILD_SCRIPT))}"
    )


# ---------------------------------------------------------------------------
# 최신성 검사와 읽기 전용 연결. 조회 스크립트와 보고서 명령이 함께 쓴다.
# ---------------------------------------------------------------------------

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


def _authorizer(action, arg1, arg2, db_name, source):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def stale_error(reason, data_dir, extra=None):
    lines = [
        reason,
        f"데이터 폴더: {data_dir}",
        f"데이터베이스: {db_path(data_dir)}",
        "아래의 명령을 실행하여 데이터베이스를 만든다.",
    ]
    if extra:
        lines.append(extra)
    lines += ["", f"  {build_command_line(data_dir)}"]
    return FtmError("\n".join(lines))


def open_checked(data_dir):
    """최신성을 검사한 뒤, 읽기 전용으로 연 연결과 생성 정보를 돌려준다."""
    current_source = source_hash(data_dir)
    current_schema = schema_hash()
    path = db_path(data_dir)
    if not path.is_file():
        raise stale_error("데이터베이스가 아직 만들어지지 않았다.", data_dir)

    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA query_only = ON")
        try:
            info = dict(conn.execute("SELECT key, value FROM build_info"))
        except sqlite3.Error:
            raise stale_error("데이터베이스에서 생성 정보를 읽을 수 없다.", data_dir)

        reasons = []
        extra = None
        if info.get("source_hash") != current_source:
            reasons.append("원본이 데이터베이스를 만든 뒤에 바뀌었다.")
        if info.get("schema_hash") != current_schema:
            reasons.append("데이터베이스가 이 스킬의 정의와 다른 정의로 만들어졌다.")
            extra = "저장소에서 정의를 고쳤다면 플러그인을 먼저 다시 설치한다."
        if reasons:
            raise stale_error(" ".join(reasons), data_dir, extra)

        conn.set_authorizer(_authorizer)
    except BaseException:
        conn.close()
        raise
    return conn, info
