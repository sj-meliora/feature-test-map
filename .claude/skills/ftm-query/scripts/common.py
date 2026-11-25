"""변환 명령과 조회 스크립트가 함께 쓰는 부분: 경로 해석, 해시 계산, 실행 줄."""

import hashlib
import os
import re
import shlex
import sqlite3
import sys
from pathlib import Path, PureWindowsPath

ENV_VAR = "FTM_DATA_DIR"

# 스크립트는 자신이 놓인 위치를 기준으로 같은 사본의 파일을 찾는다.
SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = SKILL_DIR / "schema.sql"
BUILD_SCRIPT = SKILL_DIR / "scripts" / "build.py"
# 스킬이 함께 쓰는 모듈(ftm_core)과 외부 패키지의 사본을 두는 폴더.
LIB_DIR = SKILL_DIR.parent.parent / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from ftm_core.sources import FEATURES_FILE, RELATIONS_FILE, SCENARIOS_FILE, TCS_FILE  # noqa: E402

# 원본 파일. 변환에는 네 파일이 모두 있어야 하며, 해시는 네 파일의 내용으로 계산한다.
SOURCE_FILES = (FEATURES_FILE, SCENARIOS_FILE, TCS_FILE, RELATIONS_FILE)


class FtmError(Exception):
    """사용자에게 메시지를 보이고 종료해야 하는 오류."""


def configure_output():
    """출력이 다른 프로그램으로 넘어갈 때에는 UTF-8로 쓴다.

    Windows에서는 넘겨지는 출력의 기본 인코딩이 UTF-8이 아니어서, 에이전트가 한글 메시지를 읽지 못한다.
    화면에 직접 출력할 때에는 그대로 둔다. 인코딩할 수 없는 문자 때문에 종료하지 않도록 한다.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.isatty():
                stream.reconfigure(errors="backslashreplace")
            else:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass


def resolve_data_dir(argument=None):
    """데이터 폴더의 절대 경로를 구한다. 기본 경로를 추측하지 않는다.

    변환 명령과 보고서 명령은 --data-dir 인자로도 경로를 받으며, 인자가 있으면 환경 변수보다 앞선다.
    """
    if argument is not None and argument.strip():
        path = Path(argument.strip()).expanduser().resolve()
        if not path.is_dir():
            raise FtmError(f"--data-dir이 가리키는 폴더가 없다: {path}")
        return path
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


# Windows의 셸에서 따옴표로 감싸지 않고는 명령의 이름으로 쓸 수 없는 문자.
_UNSAFE_IN_COMMAND = re.compile(r"""[\s"'&^%!$`()<>|;]""")


def command_line(script, data_dir, windows=None, executable=None):
    """스크립트를 데이터 폴더와 함께 실행하는 줄. 사용자가 그대로 복사하여 실행한다.

    데이터 폴더는 --data-dir 인자로 넣는다. 환경 변수를 줄 앞에 붙이는 표기는 셸마다 달라서 쓰지 않는다.

    Windows에서는 cmd, PowerShell, Git Bash에서 모두 읽히도록 다음과 같이 적는다.
    - 경로의 구분 문자는 '/'로 적는다. '\\'는 Git Bash에서 다음 문자와 합쳐져 사라진다.
    - 인자는 큰따옴표로 감싼다. 작은따옴표는 cmd에서 따옴표로 읽히지 않는다.
    - 실행 파일은 따옴표로 감싸지 않는다. PowerShell은 따옴표로 시작하는 줄을 명령으로 실행하지 않는다.
      경로에 공백과 같은 문자가 있어 감싸야 하는 경우에는 경로 대신 이름(python)만 적는다.
    """
    if windows is None:
        windows = os.name == "nt"
    if executable is None:
        executable = sys.executable
    if not windows:
        return (
            f"{shlex.quote(executable or 'python3')} {shlex.quote(str(script))} "
            f"--data-dir {shlex.quote(str(data_dir))}"
        )

    def posix(path):
        return PureWindowsPath(str(path)).as_posix()

    program = posix(executable) if executable else "python"
    if _UNSAFE_IN_COMMAND.search(program):
        program = "python"
    return f'{program} "{posix(script)}" --data-dir "{posix(data_dir)}"'


def build_command_line(data_dir):
    """같은 사본의 변환 명령을 실행하는 줄."""
    return command_line(BUILD_SCRIPT, data_dir)


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
