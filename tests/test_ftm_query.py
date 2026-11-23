"""ftm-query 스킬의 변환 명령과 조회 스크립트에 대한 테스트.

표준 라이브러리만 사용한다. 저장소 최상위에서 다음과 같이 실행한다.

    python3 -m unittest discover -s tests -v

예시 데이터(examples/features.yaml)를 임시 폴더에 복사하여 사용하며, 저장소의 파일은 바꾸지 않는다.
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
EXAMPLE = REPO / "examples" / "features.yaml"

HEADER = "- id: {id}\n  name: {name}\n  path: {path}\n  parent_id: {parent}\n  description: 설명이다.\n  ims_ref: REF-{id}\n"


def record(id, name=None, path=None, parent="null"):
    name = name or f"Name {id}"
    return HEADER.format(id=id, name=name, path=path or name, parent=parent)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ftm-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.data = self.tmp / "data"
        self.data.mkdir()
        shutil.copy(EXAMPLE, self.data / "features.yaml")
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

    def write_features(self, text):
        (self.data / "features.yaml").write_text(text, encoding="utf-8")

    def rows(self, result):
        """표 출력에서 머리글과 구분선을 뺀 행을 셀의 목록으로 돌려준다."""
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [l for l in result.stdout.splitlines() if l.startswith("|")]
        return [[c.strip() for c in l.strip("|").split("|")] for l in lines[2:]]

    def snapshot(self, root):
        return {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
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
        self.assertIn("- feature: 8", result.stdout)
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
        (self.data / "features.yaml").unlink()
        result = self.query("schema")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("원본 파일이 없다", result.stderr)

    def test_database_missing(self):
        line = self.assert_stale(self.query("schema"), "데이터베이스가 아직 만들어지지 않았다")
        self.assertFalse(self.db.exists(), "조회 스크립트는 데이터베이스를 만들지 않는다")
        self.assertIn(str(SKILL / "scripts" / "build.py"), line)

    def test_command_line_resolves_the_error(self):
        """오류 메시지의 실행 줄을 환경 변수 없이 그대로 실행하면 오류가 해소된다."""
        line = self.assert_stale(self.sql("SELECT 1"), "아직 만들어지지 않았다")
        env = {k: v for k, v in os.environ.items() if k != "FTM_DATA_DIR"}
        done = subprocess.run(line, shell=True, capture_output=True, text=True, env=env)
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
        self.assertIn(str(installed.resolve() / "scripts" / "build.py"), line)
        self.assertNotIn(str(SKILL), line)

        # 저장소의 변환 명령을 다시 실행해도 해소되지 않고, 실행 줄을 따르면 해소된다.
        self.assertEqual(self.build().returncode, 0)
        self.assertNotEqual(self.query("schema", skill=installed).returncode, 0)
        done = subprocess.run(line, shell=True, capture_output=True, text=True)
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
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), ["build", "features.yaml"])
        self.assertEqual([p.name for p in (self.data / "build").iterdir()], ["ftm.db"])


class RowLimit(Base):
    def test_truncated_result_is_marked(self):
        self.write_features("".join(record(f"F{i:03d}") for i in range(250)))
        self.assertEqual(self.build().returncode, 0)
        result = self.sql("SELECT id FROM feature ORDER BY id")
        self.assertEqual(len(self.rows(result)), 200)
        self.assertIn("200행을 넘어", result.stdout)
        self.assertEqual(self.rows(self.sql("SELECT COUNT(*) FROM feature")), [["250"]])

    def test_exactly_at_limit_is_not_marked(self):
        self.write_features("".join(record(f"F{i:03d}") for i in range(200)))
        self.assertEqual(self.build().returncode, 0)
        result = self.sql("SELECT id FROM feature")
        self.assertEqual(len(self.rows(result)), 200)
        self.assertIn("(200행)", result.stdout)


class Validation(Base):
    """검증 규칙(design/dp4.md)을 확인한다."""

    def assert_rejected(self, text, *expected):
        self.write_features(text)
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
        self.write_features(text)
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
        self.write_features(text)
        self.assertEqual(self.build().returncode, 0)
        self.assertEqual(self.rows(self.sql("SELECT id FROM v_leaf_feature")), [["C"]])

    def test_three_levels(self):
        text = (
            record("A", name="A") + record("B", name="B", path="A > B", parent="A")
            + record("C", name="C", path="A > B > C", parent="B") + record("D", name="D", path="A > D", parent="A")
        )
        self.write_features(text)
        self.assertEqual(self.build().returncode, 0)
        rows = self.rows(self.sql("SELECT ancestor_id, feature_id FROM v_feature_subtree ORDER BY 1, 2"))
        self.assertEqual(rows, [["A", "C"], ["A", "D"], ["B", "C"], ["C", "C"], ["D", "D"]])


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
