"""원본 파일의 이름, 필드 목록, 원본을 읽고 검사하는 함수.

스킬의 스크립트(common, build, query)를 불러오지 않는다.
"""

import json
import re
import sys
from pathlib import Path

# 외부 패키지의 사본. 이 파일이 놓인 위치를 기준으로 찾는다.
VENDOR_DIR = Path(__file__).resolve().parent.parent / "vendor"

FEATURES_FILE = "features.yaml"
SCENARIOS_FILE = "scenarios.yaml"
TCS_FILE = "tcs.jsonl"
RELATIONS_FILE = "scenario_tc.jsonl"

FEATURE_FIELDS = ("id", "name", "path", "parent_id", "description", "ims_ref")
SCENARIO_FIELDS = ("id", "feature_id", "stimulus", "environment", "response", "response_measure")
TC_FIELDS = ("id", "suite", "name", "source_file", "owner", "platform")
RELATION_FIELDS = ("scenario_id", "tc_id")
PATH_SEP = " > "
TABLE_FIELDS = (
    ("feature", FEATURE_FIELDS),
    ("scenario", SCENARIO_FIELDS),
    ("tc", TC_FIELDS),
    ("scenario_tc", RELATION_FIELDS),
)
SCENARIO_NUMBER = re.compile(r"[1-9][0-9]*")


class DuplicateKey(ValueError):
    pass


# ---------------------------------------------------------------------------
# 원본 읽기. 원본을 해석하는 부분은 아래의 두 함수에 모은다.
# ---------------------------------------------------------------------------

def load_yaml_module():
    """설치된 PyYAML이 있으면 그것을 쓰고, 없으면 함께 둔 사본을 쓴다."""
    try:
        import yaml
    except ImportError:
        sys.modules.pop("yaml", None)
        sys.path.insert(0, str(VENDOR_DIR))
        import yaml
    return yaml


def read_yaml(path):
    """YAML 원본을 읽어 (값, 오류 목록)을 돌려준다."""
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


def read_jsonl(path):
    """JSONL 원본을 읽어 ([(줄 번호, 값)], 오류 목록)을 돌려준다. 빈 줄은 건너뛴다."""

    def no_duplicates(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise DuplicateKey(key)
            obj[key] = value
        return obj

    rows, errors = [], []
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except UnicodeDecodeError as e:
        return [], [f"파일이 UTF-8이 아니다: {e}"]
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            rows.append((number, json.loads(line, object_pairs_hook=no_duplicates)))
        except DuplicateKey as e:
            errors.append(f"[{number}번째 줄] 키 {str(e)!r}가 한 레코드 안에 두 번 나온다.")
        except ValueError as e:
            errors.append(f"[{number}번째 줄] JSON을 해석할 수 없다: {e}")
    return rows, errors


# ---------------------------------------------------------------------------
# 검증 규칙(design/dp4.md). 각 함수는 (검사를 통과한 레코드, 오류 목록)을 돌려준다.
# ---------------------------------------------------------------------------

def _check_keys(tag, rec, fields, errors):
    ok = True
    for key in fields:
        if key not in rec:
            errors.append(f"{tag} 키 {key}가 없다.")
            ok = False
    for key in rec:
        if key not in fields:
            errors.append(f"{tag} 정의되지 않은 키 {key!r}가 있다.")
            ok = False
    return ok


def _check_string(tag, rec, key, errors, yaml_hint):
    """값이 비어 있지 않은 문자열인지 검사한다."""
    value = rec[key]
    if not isinstance(value, str):
        shown = "null" if value is None else repr(value)
        hint = (
            " YAML은 따옴표가 없는 값을 다른 자료형으로 해석할 수 있으므로, 값을 따옴표로 감싼다."
            if yaml_hint else ""
        )
        errors.append(f"{tag} {key}의 값 {shown}은 문자열이 아니다({type(value).__name__}).{hint}")
        return False
    if not value.strip():
        errors.append(f"{tag} {key}의 값이 비어 있다.")
        return False
    return True


def _yaml_records(data, fields, errors, nullable=()):
    """YAML 목록에서 키와 자료형의 검사를 통과한 레코드를 고른다."""
    if data is None:
        return []
    if not isinstance(data, list):
        errors.append("파일의 최상위는 레코드의 목록이어야 한다.")
        return []
    records = []
    for index, rec in enumerate(data):
        rid = rec.get("id") if isinstance(rec, dict) else None
        tag = f"[{rid}]" if isinstance(rid, str) and rid.strip() else f"[{index + 1}번째 레코드]"
        if not isinstance(rec, dict):
            errors.append(f"{tag} 레코드가 '키: 값'의 묶음이 아니다.")
            continue
        ok = _check_keys(tag, rec, fields, errors)
        for key in fields:
            if key not in rec or (key in nullable and rec[key] is None):
                continue
            ok = _check_string(tag, rec, key, errors, yaml_hint=True) and ok
        if ok:
            records.append(rec)
    return records


def _unique_by_id(records, errors, tag=lambda rec: f"[{rec['id']}]"):
    by_id = {}
    for rec in records:
        if rec["id"] in by_id:
            errors.append(f"{tag(rec)} id가 중복된다.")
        else:
            by_id[rec["id"]] = rec
    return by_id


def validate_features(data):
    errors = []
    by_id = _unique_by_id(_yaml_records(data, FEATURE_FIELDS, errors, nullable=("parent_id",)), errors)
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


def validate_scenarios(data, features):
    """features가 None이면(기능 원본에 오류가 있으면) 기능을 참조하는 규칙은 검사하지 않는다."""
    errors = []
    by_id = _unique_by_id(_yaml_records(data, SCENARIO_FIELDS, errors), errors)
    records = list(by_id.values())

    for rec in records:
        prefix = rec["feature_id"] + "-S"
        number = rec["id"][len(prefix):] if rec["id"].startswith(prefix) else ""
        if not SCENARIO_NUMBER.fullmatch(number):
            errors.append(
                f"[{rec['id']}] id가 '<기능 ID>-S<번호>' 형식이 아니다. "
                f"feature_id가 {rec['feature_id']!r}이므로 id는 {prefix + '1'!r}과 같은 형태여야 한다."
            )

    if features is not None:
        feature_ids = {f["id"] for f in features}
        parents = {f["parent_id"] for f in features if f["parent_id"] is not None}
        for rec in records:
            if rec["feature_id"] not in feature_ids:
                errors.append(f"[{rec['id']}] feature_id가 가리키는 기능 {rec['feature_id']!r}가 없다.")
            elif rec["feature_id"] in parents:
                errors.append(
                    f"[{rec['id']}] feature_id가 가리키는 기능 {rec['feature_id']!r}는 자식 항목을 가지는 묶음이다. "
                    "인스턴스 시나리오는 말단 기능에만 둔다."
                )
    return records, errors


def validate_leaf_coverage(features, scenarios):
    """모든 말단 기능은 인스턴스 시나리오를 하나 이상 가진다."""
    parents = {f["parent_id"] for f in features if f["parent_id"] is not None}
    with_scenario = {s["feature_id"] for s in scenarios}
    return [
        f"[{f['id']}] 말단 기능에 인스턴스 시나리오가 하나도 없다. {SCENARIOS_FILE}에 이 기능의 인스턴스 시나리오를 적는다."
        for f in features
        if f["id"] not in parents and f["id"] not in with_scenario
    ]


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _jsonl_records(rows, fields, errors):
    records = []
    for number, rec in rows:
        tag = f"[{number}번째 줄]"
        if not isinstance(rec, dict):
            errors.append(f"{tag} 한 줄이 JSON 객체 하나가 아니다.")
            continue
        if _check_keys(tag, rec, fields, errors):
            records.append((tag, rec))
    return records


def validate_tcs(rows, allowed):
    """allowed는 값을 제한하는 항목(owner, platform)과 그 항목에 허용하는 값의 목록이다."""
    errors = []
    records = []
    for tag, rec in _jsonl_records(rows, TC_FIELDS, errors):
        ok = True
        if not _is_int(rec["id"]) or rec["id"] < 1:
            errors.append(f"{tag} id의 값 {rec['id']!r}은 1 이상의 정수가 아니다.")
            ok = False
        for key in ("suite", "name", "source_file"):
            ok = _check_string(tag, rec, key, errors, yaml_hint=False) and ok
        for key, values in allowed.items():
            if not _check_string(tag, rec, key, errors, yaml_hint=False):
                ok = False
            elif rec[key] not in values:
                errors.append(
                    f"{tag} {key}의 값 {rec[key]!r}은 허용하는 값({', '.join(values)})이 아니다."
                )
                ok = False
        if ok:
            records.append((tag, rec))

    seen_ids, seen_names, result = set(), set(), []
    for tag, rec in records:
        ok = True
        if rec["id"] in seen_ids:
            errors.append(f"{tag} id {rec['id']}가 중복된다.")
            ok = False
        if (rec["suite"], rec["name"]) in seen_names:
            errors.append(f"{tag} suite {rec['suite']!r}와 name {rec['name']!r}의 조합이 중복된다.")
            ok = False
        seen_ids.add(rec["id"])
        seen_names.add((rec["suite"], rec["name"]))
        if ok:
            result.append(rec)
    return result, errors


def validate_relations(rows, scenarios, tcs):
    """scenarios나 tcs가 None이면(그 원본에 오류가 있으면) 그쪽을 참조하는 규칙은 검사하지 않는다."""
    errors = []
    scenario_ids = None if scenarios is None else {s["id"] for s in scenarios}
    tc_ids = None if tcs is None else {t["id"] for t in tcs}
    seen, result = set(), []
    for tag, rec in _jsonl_records(rows, RELATION_FIELDS, errors):
        ok = _check_string(tag, rec, "scenario_id", errors, yaml_hint=False)
        if not _is_int(rec["tc_id"]):
            errors.append(f"{tag} tc_id의 값 {rec['tc_id']!r}은 정수가 아니다.")
            ok = False
        if not ok:
            continue
        if scenario_ids is not None and rec["scenario_id"] not in scenario_ids:
            errors.append(f"{tag} scenario_id가 가리키는 인스턴스 시나리오 {rec['scenario_id']!r}가 없다.")
            ok = False
        if tc_ids is not None and rec["tc_id"] not in tc_ids:
            errors.append(f"{tag} tc_id가 가리키는 TC {rec['tc_id']}가 없다.")
            ok = False
        pair = (rec["scenario_id"], rec["tc_id"])
        if pair in seen:
            errors.append(f"{tag} scenario_id {pair[0]!r}와 tc_id {pair[1]}의 조합이 중복된다.")
            ok = False
        seen.add(pair)
        if ok:
            result.append(rec)
    return result, errors
