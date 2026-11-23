"""ftm-query 스킬의 변환 명령과 조회 스크립트에 대한 테스트.

표준 라이브러리만 사용한다. 저장소 최상위에서 다음과 같이 실행한다.

    python3 -m unittest discover -s tests -v

예시 데이터(examples/)를 임시 폴더에 복사하여 사용하며, 저장소의 파일은 바꾸지 않는다.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILL = REPO / ".claude" / "skills" / "ftm-query"
EXAMPLES = REPO / "examples"
SOURCES = ("features.yaml", "scenarios.yaml", "tcs.jsonl", "scenario_tc.jsonl")

HEADER = "- id: {id}\n  name: {name}\n  path: {path}\n  parent_id: {parent}\n  description: 설명이다.\n  ims_ref: REF-{id}\n"


def shown(path):
    """실행 줄에 경로가 적히는 표기. Windows에서는 구분 문자를 '/'로 적는다."""
    return Path(path).as_posix() if os.name == "nt" else str(path)


def run_line(line, env=None):
    """오류 메시지의 실행 줄을 셸에서 그대로 실행한다."""
    return subprocess.run(line, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


def record(id, name=None, path=None, parent="null"):
    name = name or f"Name {id}"
    return HEADER.format(id=id, name=name, path=path or name, parent=parent)


def scenario(id, feature_id):
    return (
        f"- id: '{id}'\n  feature_id: '{feature_id}'\n  stimulus: 자극이다.\n  environment: 환경이다.\n"
        "  response: 응답이다.\n  response_measure: 응답 측정이다.\n"
    )


def jsonl(*records):
    import json
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def tc(id, suite="suite/a", name=None, source_file="test.py"):
    return {"id": id, "suite": suite, "name": name or f"tc_{id}", "source_file": source_file}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ftm-test-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.data = self.tmp / "data"
        self.data.mkdir()
        for name in SOURCES:
            shutil.copy(EXAMPLES / name, self.data / name)
        self.db = self.data / "build" / "ftm.db"

    def run_script(self, name, *args, skill=SKILL, env_value="__data__"):
        env = {k: v for k, v in os.environ.items() if k != "FTM_DATA_DIR"}
        env["PYTHONIOENCODING"] = "utf-8"
        if env_value == "__data__":
            env["FTM_DATA_DIR"] = str(self.data)
        elif env_value is not None:
            env["FTM_DATA_DIR"] = env_value
        return subprocess.run(
            [sys.executable, str(skill / "scripts" / name), *args],
            capture_output=True, text=True, encoding="utf-8", env=env,
        )

    def build(self, **kw):
        return self.run_script("build.py", **kw)

    def query(self, *args, **kw):
        return self.run_script("query.py", *args, **kw)

    def sql(self, statement, **kw):
        return self.query("sql", statement, **kw)

    def write(self, name, text):
        (self.data / name).write_text(text, encoding="utf-8")

    def write_features(self, text, leaves=()):
        """기능 원본을 바꾸고, 나머지 원본은 leaves의 기능마다 시나리오 하나만 있는 상태로 만든다."""
        self.write("features.yaml", text)
        self.write("scenarios.yaml", "".join(scenario(f"{leaf}-S1", leaf) for leaf in leaves) or "[]\n")
        self.write("tcs.jsonl", "")
        self.write("scenario_tc.jsonl", "")

    def rows(self, result):
        """표 출력에서 머리글과 구분선을 뺀 행을 셀의 목록으로 돌려준다."""
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [l for l in result.stdout.splitlines() if l.startswith("|")]
        return [[c.strip() for c in l.strip("|").split("|")] for l in lines[2:]]

    def snapshot(self, root):
        return {
            p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()
        }


class QueryExamples(Base):
    """design/dp5.md의 '질의 예시'와 같은 결과가 나오는지 확인한다."""

    def setUp(self):
        super().setUp()
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_leaf_count(self):
        self.assertEqual(self.rows(self.sql("SELECT COUNT(*) AS leaf_count FROM v_leaf_feature")), [["7"]])

    def test_leaf_list(self):
        rows = self.rows(self.sql("SELECT id, name, path FROM v_leaf_feature ORDER BY path"))
        self.assertEqual(rows, [
            ["FLUSH", "Flush", "Flush"],
            ["FORMAT", "Format NVM", "Format NVM"],
            ["NS-CREATE", "Namespace Create", "Namespace Management > Namespace Create"],
            ["NS-DELETE", "Namespace Delete", "Namespace Management > Namespace Delete"],
            ["PS-TRANSITION", "Power State Transition", "Power State Transition"],
            ["SANITIZE", "Sanitize", "Sanitize"],
            ["SPOR", "Sudden Power-Off Recovery", "Sudden Power-Off Recovery"],
        ])

    def test_subtree_of_bundle(self):
        rows = self.rows(self.sql(
            "SELECT f.id, f.name FROM v_feature_subtree s JOIN feature f ON f.id = s.feature_id "
            "WHERE s.ancestor_id = 'NS' ORDER BY f.id"
        ))
        self.assertEqual(rows, [["NS-CREATE", "Namespace Create"], ["NS-DELETE", "Namespace Delete"]])

    def test_leaf_count_per_bundle(self):
        rows = self.rows(self.sql(
            "SELECT g.id, g.name, COUNT(*) AS leaf_count FROM feature g "
            "JOIN v_feature_subtree s ON s.ancestor_id = g.id "
            "WHERE g.id NOT IN (SELECT id FROM v_leaf_feature) GROUP BY g.id"
        ))
        self.assertEqual(rows, [["NS", "Namespace Management", "2"]])

    def test_ims_ref(self):
        rows = self.rows(self.sql("SELECT id, name, ims_ref FROM feature WHERE ims_ref = 'IMS-EX-0300'"))
        self.assertEqual(rows, [["SANITIZE", "Sanitize", "IMS-EX-0300"]])

    def test_schema_output(self):
        result = self.query("schema")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"데이터 폴더: {self.data.resolve()}", result.stdout)
        self.assertIn(f"인스턴스 시나리오 원본: {self.data.resolve() / 'scenarios.yaml'}", result.stdout)
        for line in ("- feature: 8", "- scenario: 9", "- tc: 20", "- scenario_tc: 19"):
            self.assertIn(line, result.stdout)
        for view in ("v_feature_tc", "v_scenario_tc_count", "v_feature_tc_count", "v_subtree_tc_count", "v_unlinked_tc"):
            self.assertIn(f"CREATE VIEW {view} AS", result.stdout)
        self.assertIn("CREATE TABLE feature", result.stdout)
        self.assertIn("CREATE VIEW v_leaf_feature", result.stdout)
        self.assertIn("CREATE VIEW v_feature_subtree", result.stdout)
        self.assertIn("생성 시각: ", result.stdout)

    def test_null_is_shown(self):
        rows = self.rows(self.sql("SELECT parent_id FROM feature WHERE id = 'NS'"))
        self.assertEqual(rows, [["NULL"]])


class Freshness(Base):
    """최신성 검사와 오류 메시지(design/dp6.md 2장)를 확인한다."""

    def assert_stale(self, result, reason):
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn(reason, result.stderr)
        self.assertIn(f"데이터 폴더: {self.data.resolve()}", result.stderr)
        return result.stderr.rstrip().splitlines()[-1].strip()

    def test_env_not_set(self):
        for script in ("query.py", "build.py"):
            args = ("schema",) if script == "query.py" else ()
            result = self.run_script(script, *args, env_value=None)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FTM_DATA_DIR이 설정되지 않았다", result.stderr)
            self.assertNotIn("build.py", result.stderr)
        self.assertFalse(self.db.exists())

    def test_env_points_to_missing_folder(self):
        result = self.query("schema", env_value=str(self.tmp / "nowhere"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("가리키는 폴더가 없다", result.stderr)

    def test_source_file_missing(self):
        """네 원본 중 하나라도 없으면 조회 스크립트와 변환 명령이 모두 오류로 종료한다."""
        for name in SOURCES:
            with self.subTest(name=name):
                (self.data / name).unlink()
                for result in (self.query("schema"), self.build()):
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"원본 파일이 없다: {self.data.resolve() / name}", result.stderr)
                shutil.copy(EXAMPLES / name, self.data / name)
        self.assertFalse(self.db.exists())

    def test_any_source_change_makes_database_stale(self):
        for name in SOURCES:
            with self.subTest(name=name):
                self.assertEqual(self.build().returncode, 0)
                with open(self.data / name, "a", encoding="utf-8") as f:
                    f.write("\n")
                self.assert_stale(self.sql("SELECT 1"), "원본이 데이터베이스를 만든 뒤에 바뀌었다")

    def test_database_missing(self):
        line = self.assert_stale(self.query("schema"), "데이터베이스가 아직 만들어지지 않았다")
        self.assertFalse(self.db.exists(), "조회 스크립트는 데이터베이스를 만들지 않는다")
        self.assertIn(shown(SKILL / "scripts" / "build.py"), line)
        self.assertIn(shown(self.data.resolve()), line)
        self.assertNotIn("FTM_DATA_DIR=", line, "환경 변수를 줄 앞에 붙이는 표기는 셸마다 달라서 쓰지 않는다")

    def test_command_line_resolves_the_error(self):
        """오류 메시지의 실행 줄을 환경 변수 없이 그대로 실행하면 오류가 해소된다."""
        line = self.assert_stale(self.sql("SELECT 1"), "아직 만들어지지 않았다")
        env = {k: v for k, v in os.environ.items() if k != "FTM_DATA_DIR"}
        done = run_line(line, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.rows(self.sql("SELECT COUNT(*) FROM feature")), [["8"]])

    def test_source_changed(self):
        self.assertEqual(self.build().returncode, 0)
        with open(self.data / "features.yaml", "a", encoding="utf-8") as f:
            f.write("\n# 주석 한 줄\n")
        self.assert_stale(self.sql("SELECT COUNT(*) FROM feature"), "원본이 데이터베이스를 만든 뒤에 바뀌었다")
        self.assertEqual(self.build().returncode, 0)
        self.assertEqual(self.sql("SELECT 1").returncode, 0)

    def test_two_copies_with_different_schema(self):
        """스킬의 사본이 두 곳에 있고 한쪽의 정의만 고친 상황(design/dp6.md)."""
        installed = self.tmp / "installed" / "ftm-query"
        shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns("__pycache__"))
        with open(installed / "schema.sql", "a", encoding="utf-8") as f:
            f.write("\n-- 설치된 사본에만 있는 이전 정의\n")

        # 저장소의 변환 명령으로 만들면, 설치된 조회 스크립트는 정의가 다르다고 판단한다.
        self.assertEqual(self.build().returncode, 0)
        result = self.query("schema", skill=installed)
        line = self.assert_stale(result, "이 스킬의 정의와 다른 정의로 만들어졌다")
        self.assertIn("플러그인을 먼저 다시 설치한다", result.stderr)

        # 실행 줄은 저장소가 아니라 설치된 사본의 변환 명령을 가리킨다.
        self.assertIn(shown(installed.resolve() / "scripts" / "build.py"), line)
        self.assertNotIn(shown(SKILL), line)

        # 저장소의 변환 명령을 다시 실행해도 해소되지 않고, 실행 줄을 따르면 해소된다.
        self.assertEqual(self.build().returncode, 0)
        self.assertNotEqual(self.query("schema", skill=installed).returncode, 0)
        done = run_line(line)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.query("schema", skill=installed).returncode, 0)
        # 이제 저장소의 조회 스크립트 쪽에서 정의가 다르다.
        self.assertNotEqual(self.query("schema").returncode, 0)

    def test_database_without_build_info(self):
        self.db.parent.mkdir()
        import sqlite3
        conn = sqlite3.connect(self.db)
        conn.execute("CREATE TABLE feature (id TEXT)")
        conn.commit()
        conn.close()
        self.assert_stale(self.query("schema"), "생성 정보를 읽을 수 없다")


class CommandLine(unittest.TestCase):
    """실행 줄의 표기(design/dp6.md 2장). Windows의 표기도 어느 환경에서나 확인한다."""

    def setUp(self):
        sys.path.insert(0, str(SKILL / "scripts"))
        self.addCleanup(sys.path.remove, str(SKILL / "scripts"))
        import common
        self.common = common

    def test_windows_form(self):
        line = self.common.command_line(
            r"C:\tools\ftm-query\scripts\build.py", r"D:\data\ftm", windows=True,
            executable=r"C:\Python313\python.exe",
        )
        self.assertEqual(line, 'C:/Python313/python.exe "C:/tools/ftm-query/scripts/build.py" --data-dir "D:/data/ftm"')

    def test_windows_form_avoids_quoting_the_program(self):
        """실행 파일의 경로에 공백이 있으면 경로 대신 이름만 적는다. 따옴표로 시작하는 줄은 PowerShell에서 실행되지 않는다."""
        line = self.common.command_line(
            r"C:\tools\build.py", r"D:\my data", windows=True,
            executable=r"C:\Program Files\Python313\python.exe",
        )
        self.assertEqual(line, 'python "C:/tools/build.py" --data-dir "D:/my data"')
        self.assertFalse(line.startswith('"'))

    def test_windows_form_has_no_backslash_or_single_quote(self):
        line = self.common.command_line(r"C:\a\build.py", r"C:\b", windows=True, executable=r"C:\py\python.exe")
        self.assertNotIn("\\", line)
        self.assertNotIn("'", line)
        self.assertNotIn("FTM_DATA_DIR", line)

    def test_posix_form(self):
        line = self.common.command_line("/opt/ftm/build.py", "/data/my data", windows=False, executable="/usr/bin/python3")
        self.assertEqual(line, "/usr/bin/python3 /opt/ftm/build.py --data-dir '/data/my data'")


class DataDirArgument(Base):
    """변환 명령은 --data-dir 인자로도 데이터 폴더를 받는다."""

    def test_argument_without_environment(self):
        result = self.run_script("build.py", "--data-dir", str(self.data), env_value=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.db.is_file())

    def test_argument_wins_over_environment(self):
        other = self.tmp / "other"
        other.mkdir()
        result = self.run_script("build.py", "--data-dir", str(self.data), env_value=str(other))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.db.is_file())
        self.assertFalse((other / "build").exists())

    def test_argument_points_to_missing_folder(self):
        result = self.run_script("build.py", "--data-dir", str(self.tmp / "nowhere"), env_value=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--data-dir이 가리키는 폴더가 없다", result.stderr)


class CheckFeatures(Base):
    """기능 원본 하나만 검사하는 --check-features. 환경 변수와 다른 원본이 없어도 동작한다."""

    def check(self, path):
        return self.run_script("build.py", "--check-features", str(path), env_value=None)

    def test_valid_file(self):
        result = self.check(EXAMPLES / "features.yaml")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("기능 레코드: 8개 (묶음 1개, 검증 대상 7개)", result.stdout)
        self.assertFalse(self.db.exists())

    def test_file_alone_in_a_folder(self):
        alone = self.tmp / "alone"
        alone.mkdir()
        shutil.copy(EXAMPLES / "features.yaml", alone / "draft.yaml")
        result = self.check(alone / "draft.yaml")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([p.name for p in alone.iterdir()], ["draft.yaml"])

    def test_errors_are_reported(self):
        draft = self.tmp / "draft.yaml"
        draft.write_text(
            "- id: NO\n  name: A\n  path: B\n  parent_id: null\n  description: 설명이다.\n", encoding="utf-8"
        )
        result = self.check(draft)
        self.assertEqual(result.returncode, 1)
        self.assertIn("오류 2개", result.stderr)
        self.assertIn("키 ims_ref가 없다", result.stderr)
        self.assertIn("따옴표로 감싼다", result.stderr)

    def test_missing_file(self):
        result = self.check(self.tmp / "none.yaml")
        self.assertEqual(result.returncode, 2)
        self.assertIn("파일이 없다", result.stderr)


class Output(Base):
    def test_piped_output_is_utf8_regardless_of_locale(self):
        """출력이 다른 프로그램으로 넘어갈 때에는 환경의 기본 인코딩과 무관하게 UTF-8로 쓴다."""
        env = {k: v for k, v in os.environ.items() if k not in ("FTM_DATA_DIR", "PYTHONIOENCODING", "PYTHONUTF8")}
        env.update(LC_ALL="C", LANG="C", PYTHONCOERCECLOCALE="0")
        result = subprocess.run(
            [sys.executable, "-X", "utf8=0", str(SKILL / "scripts" / "query.py"), "schema"],
            capture_output=True, env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FTM_DATA_DIR이 설정되지 않았다", result.stderr.decode("utf-8"))


class ReadOnly(Base):
    """읽기 전용의 보장(design/dp6.md 3장)을 확인한다."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.build().returncode, 0)

    def test_writes_are_rejected(self):
        outside = self.tmp / "outside.db"
        statements = [
            "DELETE FROM feature",
            "UPDATE feature SET name = 'x'",
            "INSERT INTO feature VALUES ('a','a','a',NULL,'a','a')",
            "DROP TABLE feature",
            "CREATE TABLE t (a)",
            f"ATTACH DATABASE '{outside}' AS x",
            "PRAGMA writable_schema = 1",
            "PRAGMA query_only = OFF",
            "VACUUM",
        ]
        before = self.snapshot(self.data)
        for statement in statements:
            result = self.sql(statement)
            self.assertNotEqual(result.returncode, 0, statement)
            self.assertRegex(result.stderr, "not authorized|authorization denied", statement)
            self.assertIn("읽기 전용", result.stderr, statement)
        self.assertEqual(self.snapshot(self.data), before)
        self.assertFalse(outside.exists())

    def test_only_one_statement(self):
        result = self.sql("SELECT 1; DELETE FROM feature")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.rows(self.sql("SELECT COUNT(*) FROM feature")), [["8"]])

    def test_query_writes_no_file(self):
        """조회 스크립트는 데이터 폴더와 스킬 폴더에 어떤 파일도 쓰지 않는다."""
        installed = self.tmp / "installed" / "ftm-query"
        shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns("__pycache__"))
        self.assertEqual(self.build(skill=installed).returncode, 0)
        before = (self.snapshot(self.data), self.snapshot(installed))
        self.assertEqual(self.query("schema", skill=installed).returncode, 0)
        self.assertEqual(self.sql("SELECT * FROM v_feature_subtree", skill=installed).returncode, 0)
        self.assertNotEqual(self.sql("DELETE FROM feature", skill=installed).returncode, 0)
        self.assertEqual((self.snapshot(self.data), self.snapshot(installed)), before)

    def test_build_does_not_change_source(self):
        before = (self.data / "features.yaml").read_bytes()
        self.assertEqual(self.build().returncode, 0)
        self.assertEqual((self.data / "features.yaml").read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), sorted(("build",) + SOURCES))
        self.assertEqual([p.name for p in (self.data / "build").iterdir()], ["ftm.db"])


class RowLimit(Base):
    def test_truncated_result_is_marked(self):
        ids = [f"F{i:03d}" for i in range(250)]
        self.write_features("".join(record(i) for i in ids), leaves=ids)
        self.assertEqual(self.build().returncode, 0)
        result = self.sql("SELECT id FROM feature ORDER BY id")
        self.assertEqual(len(self.rows(result)), 200)
        self.assertIn("200행을 넘어", result.stdout)
        self.assertEqual(self.rows(self.sql("SELECT COUNT(*) FROM feature")), [["250"]])

    def test_exactly_at_limit_is_not_marked(self):
        ids = [f"F{i:03d}" for i in range(200)]
        self.write_features("".join(record(i) for i in ids), leaves=ids)
        self.assertEqual(self.build().returncode, 0)
        result = self.sql("SELECT id FROM feature")
        self.assertEqual(len(self.rows(result)), 200)
        self.assertIn("(200행)", result.stdout)


class Validation(Base):
    """검증 규칙(design/dp4.md)을 확인한다."""

    def assert_rejected(self, text, *expected):
        self.write_features(text)
        return self.assert_build_fails(*expected)

    def assert_build_fails(self, *expected):
        result = self.build()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("데이터베이스를 만들지 않았다", result.stderr)
        for fragment in expected:
            self.assertIn(fragment, result.stderr)
        return result

    def test_missing_and_unknown_key(self):
        text = "- id: A\n  name: A\n  path: A\n  parent_id: null\n  descripton: 오타다.\n  ims_ref: R\n"
        self.assert_rejected(text, "[A] 키 description가 없다", "[A] 정의되지 않은 키 'descripton'가 있다")

    def test_parent_id_key_must_be_present(self):
        text = "- id: A\n  name: A\n  path: A\n  description: 설명이다.\n  ims_ref: R\n"
        self.assert_rejected(text, "[A] 키 parent_id가 없다")

    def test_yaml_type_coercion(self):
        text = (
            "- id: NO\n  name: 1.10\n  path: x\n  parent_id: null\n  description: 설명이다.\n  ims_ref: 0100\n"
        )
        result = self.assert_rejected(text, "id의 값 False", "name의 값 1.1", "ims_ref의 값 64", "따옴표로 감싼다")
        self.assertIn("[1번째 레코드]", result.stderr)

    def test_quoted_values_are_accepted(self):
        text = (
            "- id: 'NO'\n  name: '1.10'\n  path: '1.10'\n  parent_id: null\n  description: 설명이다.\n  ims_ref: '0100'\n"
        )
        self.write_features(text, leaves=["NO"])
        self.assertEqual(self.build().returncode, 0)
        self.assertEqual(self.rows(self.sql("SELECT id, name, ims_ref FROM feature")), [["NO", "1.10", "0100"]])

    def test_empty_value(self):
        text = "- id: A\n  name: ''\n  path: A\n  parent_id: null\n  description: null\n  ims_ref: R\n"
        self.assert_rejected(text, "[A] name의 값이 비어 있다", "[A] description의 값 null은 문자열이 아니다")

    def test_duplicate_id(self):
        self.assert_rejected(record("A") + record("A"), "[A] id가 중복된다")

    def test_duplicate_key_in_record(self):
        text = "- id: A\n  name: A\n  name: B\n  path: A\n  parent_id: null\n  description: 설명이다.\n  ims_ref: R\n"
        self.assert_rejected(text, "'name'가 한 레코드 안에 두 번 나온다")

    def test_missing_parent(self):
        self.assert_rejected(record("A", parent="NOPE"), "[A] parent_id가 가리키는 기능 'NOPE'가 없다")

    def test_cycle(self):
        text = record("A", parent="B") + record("B", parent="A")
        self.assert_rejected(text, "[A] 부모를 따라 올라가면 자신으로 돌아온다", "[B] 부모를 따라 올라가면 자신으로 돌아온다")

    def test_self_parent(self):
        self.assert_rejected(record("A", parent="A"), "[A] 부모를 따라 올라가면 자신으로 돌아온다")

    def test_path_mismatch(self):
        text = record("P", name="Parent") + record("C", name="Child", path="Child", parent="P")
        self.assert_rejected(text, "[C] path가 'Child'이지만", "'Parent > Child'")

    def test_top_level_path_must_equal_name(self):
        self.assert_rejected(record("A", name="Alpha", path="Other"), "[A] path가 'Other'이지만")

    def test_all_errors_are_reported(self):
        text = record("A") + record("A") + record("B", parent="NOPE") + record("C", name="C", path="wrong")
        result = self.assert_rejected(text, "[A] id가 중복된다", "[B] parent_id", "[C] path")
        self.assertIn("오류 3개", result.stderr)

    def test_not_a_list(self):
        self.assert_rejected("id: A\nname: A\n", "최상위는 레코드의 목록이어야 한다")

    def test_broken_yaml(self):
        self.assert_rejected("- id: [A\n", "YAML을 해석할 수 없다")

    def test_existing_database_is_kept_on_error(self):
        self.assertEqual(self.build().returncode, 0)
        before = self.db.read_bytes()
        self.assert_rejected(record("A") + record("A"), "id가 중복된다")
        self.assertEqual(self.db.read_bytes(), before)
        self.assertEqual([p.name for p in self.db.parent.iterdir()], ["ftm.db"])

    def test_record_order_is_free(self):
        """자식 항목이 부모 항목보다 먼저 적혀 있어도 변환된다(design/dp1.md)."""
        text = record("C", name="Child", path="Parent > Child", parent="P") + record("P", name="Parent")
        self.write_features(text, leaves=["C"])
        self.assertEqual(self.build().returncode, 0)
        self.assertEqual(self.rows(self.sql("SELECT id FROM v_leaf_feature")), [["C"]])

    def test_three_levels(self):
        text = (
            record("A", name="A") + record("B", name="B", path="A > B", parent="A")
            + record("C", name="C", path="A > B > C", parent="B") + record("D", name="D", path="A > D", parent="A")
        )
        self.write_features(text, leaves=["C", "D"])
        self.assertEqual(self.build().returncode, 0)
        rows = self.rows(self.sql("SELECT ancestor_id, feature_id FROM v_feature_subtree ORDER BY 1, 2"))
        self.assertEqual(rows, [["A", "C"], ["A", "D"], ["B", "C"], ["C", "C"], ["D", "D"]])


class AggregateViews(Base):
    """집계 뷰(design/dp5.md 3장)가 예시 데이터에서 내는 결과를 확인한다."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.build().returncode, 0)

    def test_scenario_tc_count(self):
        rows = self.rows(self.sql("SELECT scenario_id, feature_id, tc_count FROM v_scenario_tc_count ORDER BY 1"))
        self.assertEqual(rows, [
            ["FLUSH-S1", "FLUSH", "3"],
            ["FORMAT-S1", "FORMAT", "3"],
            ["NS-CREATE-S1", "NS-CREATE", "3"],
            ["NS-CREATE-S2", "NS-CREATE", "1"],
            ["NS-DELETE-S1", "NS-DELETE", "2"],
            ["PS-TRANSITION-S1", "PS-TRANSITION", "0"],
            ["SANITIZE-S1", "SANITIZE", "3"],
            ["SANITIZE-S2", "SANITIZE", "0"],
            ["SPOR-S1", "SPOR", "4"],
        ])

    def test_feature_tc_count(self):
        rows = self.rows(self.sql(
            "SELECT feature_id, scenario_count, uncovered_scenario_count, tc_count FROM v_feature_tc_count ORDER BY 1"
        ))
        self.assertEqual(rows, [
            ["FLUSH", "1", "0", "3"],
            ["FORMAT", "1", "0", "3"],
            ["NS-CREATE", "2", "0", "4"],
            ["NS-DELETE", "1", "0", "2"],
            ["PS-TRANSITION", "1", "1", "0"],
            ["SANITIZE", "2", "1", "3"],
            ["SPOR", "1", "0", "4"],
        ])

    def test_subtree_counts_shared_tc_once(self):
        """두 기능을 함께 검증하는 TC는 묶음에서 한 번만 센다(4 + 2가 아니라 5)."""
        rows = self.rows(self.sql(
            "SELECT feature_id, leaf_count, uncovered_leaf_count, tc_count FROM v_subtree_tc_count "
            "WHERE feature_id IN ('NS', 'NS-CREATE', 'NS-DELETE', 'PS-TRANSITION') ORDER BY 1"
        ))
        self.assertEqual(rows, [
            ["NS", "2", "0", "5"],
            ["NS-CREATE", "1", "0", "4"],
            ["NS-DELETE", "1", "0", "2"],
            ["PS-TRANSITION", "1", "1", "0"],
        ])

    def test_gaps(self):
        self.assertEqual(
            self.rows(self.sql("SELECT scenario_id FROM v_scenario_tc_count WHERE tc_count = 0 ORDER BY 1")),
            [["PS-TRANSITION-S1"], ["SANITIZE-S2"]],
        )
        self.assertEqual(
            self.rows(self.sql("SELECT feature_id FROM v_feature_tc_count WHERE tc_count = 0")),
            [["PS-TRANSITION"]],
        )

    def test_feature_tc_and_unlinked_tc(self):
        self.assertEqual(
            self.rows(self.sql("SELECT COUNT(*), COUNT(DISTINCT tc_id) FROM v_feature_tc")), [["19", "17"]]
        )
        self.assertEqual(
            self.rows(self.sql("SELECT feature_id FROM v_feature_tc WHERE tc_id = 17 ORDER BY 1")),
            [["FLUSH"], ["SPOR"]],
        )
        self.assertEqual(self.rows(self.sql("SELECT id FROM v_unlinked_tc ORDER BY id")), [["18"], ["19"], ["20"]])


class OtherSourceValidation(Base):
    """인스턴스 시나리오, TC, 시나리오-TC 관계의 검증 규칙(design/dp4.md 4장)을 확인한다."""

    def setUp(self):
        super().setUp()
        # 묶음 P 아래에 말단 A와 B가 있고, 각 말단에 시나리오가 하나씩 있는 최소 데이터.
        self.features = (
            record("P", name="P") + record("A", name="A", path="P > A", parent="P")
            + record("B", name="B", path="P > B", parent="P")
        )
        self.write_features(self.features, leaves=["A", "B"])
        self.good_scenarios = scenario("A-S1", "A") + scenario("B-S1", "B")

    def fails(self, *expected, count=None):
        result = self.build()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("데이터베이스를 만들지 않았다", result.stderr)
        self.assertFalse(self.db.exists())
        for fragment in expected:
            self.assertIn(fragment, result.stderr)
        if count is not None:
            self.assertIn(f"오류 {count}개", result.stderr)
        return result

    def test_minimal_data_builds(self):
        self.assertEqual(self.build().returncode, 0)
        self.assertEqual(self.rows(self.sql("SELECT COUNT(*) FROM scenario")), [["2"]])

    def test_leaf_without_scenario(self):
        self.write("scenarios.yaml", scenario("A-S1", "A"))
        self.fails("scenarios.yaml: [B] 말단 기능에 인스턴스 시나리오가 하나도 없다", count=1)

    def test_scenario_on_bundle(self):
        self.write("scenarios.yaml", self.good_scenarios + scenario("P-S1", "P"))
        self.fails("scenarios.yaml: [P-S1] feature_id가 가리키는 기능 'P'는 자식 항목을 가지는 묶음이다", count=1)

    def test_scenario_feature_missing(self):
        self.write("scenarios.yaml", self.good_scenarios + scenario("X-S1", "X"))
        self.fails("scenarios.yaml: [X-S1] feature_id가 가리키는 기능 'X'가 없다", count=1)

    def test_scenario_id_format(self):
        for bad in ("A-1", "B-S2", "A-S0", "A-S01", "A-S", "A-S1x", "S1"):
            with self.subTest(id=bad):
                self.write("scenarios.yaml", self.good_scenarios + scenario(bad, "A"))
                self.fails(f"scenarios.yaml: [{bad}] id가 '<기능 ID>-S<번호>' 형식이 아니다")

    def test_scenario_duplicate_id_and_keys(self):
        self.write("scenarios.yaml", self.good_scenarios + scenario("A-S1", "A"))
        self.fails("scenarios.yaml: [A-S1] id가 중복된다")
        self.write("scenarios.yaml", self.good_scenarios.replace("  response: 응답이다.\n", "", 1))
        self.fails("scenarios.yaml: [A-S1] 키 response가 없다")
        self.write("scenarios.yaml", self.good_scenarios.replace("stimulus: 자극이다.", "stimulus: ''", 1))
        self.fails("scenarios.yaml: [A-S1] stimulus의 값이 비어 있다")

    def test_second_scenario_is_accepted(self):
        self.write("scenarios.yaml", self.good_scenarios + scenario("A-S2", "A") + scenario("A-S10", "A"))
        self.assertEqual(self.build().returncode, 0)
        self.assertEqual(
            self.rows(self.sql("SELECT scenario_count FROM v_feature_tc_count WHERE feature_id = 'A'")), [["3"]]
        )

    def test_scenario_errors_are_skipped_when_features_are_broken(self):
        """기능 원본에 오류가 있으면, 기능을 참조하는 규칙의 오류를 덧붙이지 않는다."""
        self.write("features.yaml", record("A") + record("A"))
        self.fails("features.yaml: [A] id가 중복된다", count=1)

    def test_tc_rules(self):
        self.write("tcs.jsonl", jsonl(tc(1), tc(1, name="other"), tc(2, name="tc_1"), tc(0), tc(True), tc("3"), tc(4, suite="")) + "[1, 2]\nnot json\n")
        result = self.fails(
            "tcs.jsonl: [2번째 줄] id 1가 중복된다",
            "tcs.jsonl: [3번째 줄] suite 'suite/a'와 name 'tc_1'의 조합이 중복된다",
            "tcs.jsonl: [4번째 줄] id의 값 0은 1 이상의 정수가 아니다",
            "tcs.jsonl: [5번째 줄] id의 값 True은 1 이상의 정수가 아니다",
            "tcs.jsonl: [6번째 줄] id의 값 '3'은 1 이상의 정수가 아니다",
            "tcs.jsonl: [7번째 줄] suite의 값이 비어 있다",
            "tcs.jsonl: [8번째 줄] 한 줄이 JSON 객체 하나가 아니다",
            "tcs.jsonl: [9번째 줄] JSON을 해석할 수 없다",
            count=8,
        )
        self.assertNotIn("따옴표", result.stderr)

    def test_tc_keys(self):
        self.write("tcs.jsonl", '{"id": 1, "suite": "s", "name": "n"}\n{"id": 2, "suite": "s", "name": "m", "source_file": "f", "x": 1}\n{"id": 3, "id": 4, "suite": "s", "name": "k", "source_file": "f"}\n')
        self.fails(
            "tcs.jsonl: [1번째 줄] 키 source_file가 없다",
            "tcs.jsonl: [2번째 줄] 정의되지 않은 키 'x'가 있다",
            "tcs.jsonl: [3번째 줄] 키 'id'가 한 레코드 안에 두 번 나온다",
            count=3,
        )

    def test_blank_lines_are_skipped(self):
        self.write("tcs.jsonl", "\n" + jsonl(tc(1)) + "\n\n" + jsonl(tc(2)) + "\n")
        self.write("scenario_tc.jsonl", "\n" + jsonl({"scenario_id": "A-S1", "tc_id": 2}))
        self.assertEqual(self.build().returncode, 0)
        self.assertEqual(self.rows(self.sql("SELECT COUNT(*) FROM tc")), [["2"]])
        self.assertEqual(self.rows(self.sql("SELECT id FROM v_unlinked_tc")), [["1"]])

    def test_relation_rules(self):
        self.write("tcs.jsonl", jsonl(tc(1), tc(2)))
        self.write("scenario_tc.jsonl", jsonl(
            {"scenario_id": "A-S1", "tc_id": 1},
            {"scenario_id": "A-S1", "tc_id": 1},
            {"scenario_id": "A-S9", "tc_id": 1},
            {"scenario_id": "B-S1", "tc_id": 7},
            {"scenario_id": "B-S1", "tc_id": "2"},
            {"scenario_id": "B-S1"},
        ))
        self.fails(
            "scenario_tc.jsonl: [2번째 줄] scenario_id 'A-S1'와 tc_id 1의 조합이 중복된다",
            "scenario_tc.jsonl: [3번째 줄] scenario_id가 가리키는 인스턴스 시나리오 'A-S9'가 없다",
            "scenario_tc.jsonl: [4번째 줄] tc_id가 가리키는 TC 7가 없다",
            "scenario_tc.jsonl: [5번째 줄] tc_id의 값 '2'은 정수가 아니다",
            "scenario_tc.jsonl: [6번째 줄] 키 tc_id가 없다",
            count=5,
        )

    def test_errors_in_all_files_are_reported_together(self):
        self.write("scenarios.yaml", scenario("A-S1", "A"))
        self.write("tcs.jsonl", jsonl(tc(1), tc(1, name="x")))
        self.write("scenario_tc.jsonl", jsonl({"scenario_id": "A-S1", "tc_id": 1, "role": "x"}))
        self.fails("scenarios.yaml: [B]", "tcs.jsonl: [2번째 줄]", "scenario_tc.jsonl: [1번째 줄]", count=3)


class VendoredYaml(Base):
    def test_build_works_without_installed_pyyaml(self):
        """PyYAML이 설치되지 않은 환경에서는 스킬에 포함한 사본으로 변환한다."""
        scripts = SKILL / "scripts"
        code = (
            "import sys\n"
            "sys.dont_write_bytecode = True\n"
            "sys.modules['yaml'] = None\n"  # import yaml이 ImportError를 내게 한다.
            f"sys.path.insert(0, {str(scripts)!r})\n"
            "import build\n"
            "rc = build.main()\n"
            "import yaml\n"
            "print('YAML_FROM', yaml.__file__)\n"
            "sys.exit(rc)\n"
        )
        env = dict(os.environ, FTM_DATA_DIR=str(self.data), PYTHONIOENCODING="utf-8")
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(SKILL / "vendor" / "yaml"), result.stdout)
        self.assertEqual(self.rows(self.sql("SELECT COUNT(*) FROM feature")), [["8"]])


if __name__ == "__main__":
    unittest.main()
