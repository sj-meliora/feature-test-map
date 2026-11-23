"""보고서 명령(report/report.py)에 대한 테스트.

표준 라이브러리만 사용한다. 저장소 최상위에서 다음과 같이 실행한다.

    python3 -m unittest discover -s tests -v

보고서에 넣은 데이터가 집계 뷰와 일치하는지, 최신성 검사와 파일 쓰기가 설계대로인지 확인한다.
화면이 브라우저에서 그려지는 모습은 확인하지 않는다.
"""

import json
import re
import shutil

from test_ftm_query import Base, SKILL, record


def embedded_data(html):
    match = re.search(r'<script type="application/json" id="ftm-data">(.*?)</script>', html, re.S)
    assert match, "보고서에 데이터가 들어 있지 않다"
    return json.loads(match.group(1))


class Report(Base):
    def setUp(self):
        super().setUp()
        self.report = self.data / "build" / "report.html"

    def make(self, skill=SKILL):
        return self.run_script("../report/report.py", skill=skill)

    def built(self):
        self.assertEqual(self.build().returncode, 0)
        result = self.make()
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.report.read_text(encoding="utf-8")

    def test_data_matches_views(self):
        data = embedded_data(self.built())
        self.assertEqual(data["totals"], {
            "leaf_count": 7, "uncovered_leaf_count": 1,
            "scenario_count": 9, "uncovered_scenario_count": 2,
            "tc_count": 20, "unlinked_tc_count": 3,
        })
        features = {f["id"]: f for f in data["features"]}
        self.assertEqual(
            [f["id"] for f in data["features"]],
            ["NS", "NS-CREATE", "NS-DELETE", "FORMAT", "SANITIZE", "FLUSH", "PS-TRANSITION", "SPOR"],
        )
        self.assertFalse(features["NS"]["is_leaf"])
        self.assertEqual((features["NS"]["leaf_count"], features["NS"]["tc_count"]), (2, 5))
        self.assertEqual((features["NS"]["depth"], features["NS-CREATE"]["depth"]), (0, 1))
        self.assertEqual(features["PS-TRANSITION"]["tc_count"], 0)
        self.assertEqual(
            (features["SANITIZE"]["scenario_count"], features["SANITIZE"]["uncovered_scenario_count"]), (2, 1)
        )
        scenarios = {s["id"]: s for s in data["scenarios"]}
        self.assertEqual(scenarios["NS-CREATE-S1"]["tc_ids"], [1, 2, 4])
        self.assertEqual((scenarios["SANITIZE-S2"]["tc_count"], scenarios["SANITIZE-S2"]["tc_ids"]), (0, []))
        self.assertEqual(data["tc_features"], {"4": ["NS-CREATE", "NS-DELETE"], "17": ["FLUSH", "SPOR"]})
        self.assertEqual(data["unlinked_tc_ids"], [18, 19, 20])
        self.assertEqual(len(data["tcs"]), 20)
        self.assertEqual(data["meta"]["data_dir"], str(self.data.resolve()))

    def test_report_is_a_single_self_contained_file(self):
        html = self.built()
        self.assertTrue(html.startswith("<!doctype html>"))
        self.assertIn("<title>FTM 검증 공백 보고서</title>", html)
        self.assertNotRegex(html, r"https?://", "보고서는 외부 자원을 불러오지 않는다")
        self.assertNotIn("/*__DATA__*/", html)
        self.assertEqual(sorted(p.name for p in self.report.parent.iterdir()), ["ftm.db", "report.html"])

    def test_text_cannot_close_the_script_element(self):
        text = record("A").replace("설명이다.", "'</script><script>alert(1)</script> & <b>굵게</b>'")
        self.write_features(text, leaves=["A"])
        html = self.built()
        self.assertEqual(html.count("</script>"), 2)
        self.assertEqual(embedded_data(html)["features"][0]["description"], "</script><script>alert(1)</script> & <b>굵게</b>")

    def test_database_missing_or_stale(self):
        result = self.make()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("데이터베이스가 아직 만들어지지 않았다", result.stderr)
        self.assertIn(str(SKILL / "scripts" / "build.py"), result.stderr.rstrip().splitlines()[-1])
        self.assertFalse(self.report.parent.exists(), "보고서 명령은 데이터베이스를 만들지 않는다")

        old = self.built()
        with open(self.data / "tcs.jsonl", "a", encoding="utf-8") as f:
            f.write("\n")
        result = self.make()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("원본이 데이터베이스를 만든 뒤에 바뀌었다", result.stderr)
        self.assertEqual(self.report.read_text(encoding="utf-8").split('"generated_at"')[0], old.split('"generated_at"')[0])

    def test_report_writes_only_the_report(self):
        installed = self.tmp / "installed" / "ftm-query"
        shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns("__pycache__"))
        self.assertEqual(self.build(skill=installed).returncode, 0)
        before = (self.snapshot(self.data), self.snapshot(installed))
        self.assertEqual(self.make(skill=installed).returncode, 0)
        after = self.snapshot(self.data)
        self.assertEqual(set(after) - set(before[0]), {"build/report.html"})
        self.assertEqual({k: v for k, v in after.items() if k != "build/report.html"}, before[0])
        self.assertEqual(self.snapshot(installed), before[1])

    def test_report_depends_only_on_common(self):
        """보고서 명령은 조회 스크립트와 변환 명령을 불러오지 않는다. 나중에 분리할 수 있게 하기 위해서다."""
        source = (SKILL / "report" / "report.py").read_text(encoding="utf-8")
        imported = set(re.findall(r"^(?:import|from)\s+([\w.]+)", source, re.M))
        self.assertIn("common", imported)
        self.assertFalse(imported & {"query", "build"})

    def test_env_not_set(self):
        result = self.run_script("../report/report.py", env_value=None)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("FTM_DATA_DIR이 설정되지 않았다", result.stderr)

    def test_deep_tree_order(self):
        text = (
            record("A", name="A") + record("B", name="B", path="A > B", parent="A")
            + record("Z", name="Z") + record("C", name="C", path="A > B > C", parent="B")
            + record("D", name="D", path="A > D", parent="A")
        )
        self.write_features(text, leaves=["C", "D", "Z"])
        data = embedded_data(self.built())
        self.assertEqual([(f["id"], f["depth"]) for f in data["features"]], [("A", 0), ("B", 1), ("C", 2), ("D", 1), ("Z", 0)])


if __name__ == "__main__":
    import unittest
    unittest.main()
