"""변환 명령과 조회 스크립트가 함께 쓰는 부분: 경로 해석, 해시 계산, 실행 줄."""

import hashlib
import os
import shlex
import sys
from pathlib import Path

ENV_VAR = "FTM_DATA_DIR"

# 스크립트는 자신이 놓인 위치를 기준으로 같은 사본의 파일을 찾는다.
SKILL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = SKILL_DIR / "schema.sql"
BUILD_SCRIPT = SKILL_DIR / "scripts" / "build.py"
VENDOR_DIR = SKILL_DIR / "vendor"

FEATURES_FILE = "features.yaml"
# 해시에 포함하는 원본 파일. 테이블이 추가되면 이 목록에 원본 파일을 추가한다.
SOURCE_FILES = (FEATURES_FILE,)


class FtmError(Exception):
    """사용자에게 메시지를 보이고 종료해야 하는 오류."""


def resolve_data_dir():
    """환경 변수에서 데이터 폴더의 절대 경로를 구한다. 기본 경로를 추측하지 않는다."""
    value = os.environ.get(ENV_VAR, "").strip()
    if not value:
        raise FtmError(
            f"환경 변수 {ENV_VAR}이 설정되지 않았다.\n"
            f"데이터 폴더({FEATURES_FILE}이 있는 폴더)의 경로를 {ENV_VAR}에 설정한 뒤 다시 실행한다."
        )
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise FtmError(
            f"{ENV_VAR}이 가리키는 폴더가 없다: {path}\n"
            f"데이터 폴더({FEATURES_FILE}이 있는 폴더)의 경로를 {ENV_VAR}에 설정한 뒤 다시 실행한다."
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
            raise FtmError(f"원본 파일이 없다: {path}\n데이터 폴더: {data_dir}")
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
