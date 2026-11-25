---
name: ftm-query
description: Feature-Test Map의 데이터(SSD FW의 기능, 인스턴스 시나리오, TC, 시나리오-TC 관계)를 읽기 전용으로 조회한다. 기능과 인스턴스 시나리오의 내용, 기능을 검증하는 TC의 개수와 목록, 검증 공백(TC가 연결되지 않은 인스턴스 시나리오와 기능), TC의 운영 조직(sv, sw-dev)과 실행 환경(msvp, hapsim)별 검증 공백, 묶음 기능 단위의 집계에 대한 질의에 답할 때 사용한다.
---

# ftm-query

Feature-Test Map의 데이터를 조회하여 질의에 답하는 절차다. 데이터는 기능, 인스턴스 시나리오, TC, 시나리오-TC 관계의 네 테이블로 구성된다.

## 명령

아래에서 `<skill>`은 이 `SKILL.md`가 있는 폴더의 경로다. `python3`이 없는 환경(Windows 등)에서는 `python`으로 실행한다.

| 명령 | 동작 |
|---|---|
| `python3 <skill>/scripts/query.py schema` | 데이터 폴더의 절대 경로, 테이블과 뷰의 정의, 테이블별 레코드 수, 생성 시각을 출력한다. |
| `python3 <skill>/scripts/query.py sql "<SELECT 문>"` | SELECT 문 한 문장을 실행하고 결과를 표로 출력한다. |

조회 스크립트는 읽기 전용이다. SELECT 문 이외의 문장은 거부된다.

## 조회 절차

1. `schema` 명령을 실행하여 데이터 폴더의 경로와 테이블, 뷰의 정의를 확인한다. 데이터 폴더의 경로는 이 출력에서만 얻으며, 환경 변수를 직접 읽거나 경로를 추측하지 않는다.
2. 출력의 '기능 원본'에 적힌 `features.yaml`과 '인스턴스 시나리오 원본'에 적힌 `scenarios.yaml`을 처음부터 끝까지 전부 읽는다.
3. 질의에 나오는 기능과 인스턴스 시나리오를 ID로 바꾼다. 의미로 찾아야 하는 경우에는 기능의 `name`, `path`, `description`과 인스턴스 시나리오의 `stimulus`, `environment`, `response`, `response_measure`를 근거로 판단한다. 해당하는 대상이 여럿이면 모두 고른다.
4. TC와 관계에 대한 질의, 그리고 개수, 검증 대상 여부, 하위 트리처럼 계산이 필요한 질의는 `sql` 명령으로 구한다. 가능하면 뷰를 사용한다. TC와 관계의 원본 파일(`tcs.jsonl`, `scenario_tc.jsonl`)은 읽지 않는다.
5. 개수는 반드시 `COUNT`나 뷰의 개수 열로 구하고, 결과 행을 세지 않는다. 조회 스크립트는 결과를 200행까지만 출력하므로, 잘린 결과를 세면 개수가 틀린다.
6. 응답에 근거로 기능 ID, 인스턴스 시나리오 ID, TC의 `id`와 `suite`, `name`을 인용한다. 분류를 지정한 질의에는 TC의 `owner`나 `platform`도 함께 인용한다. SQL을 실행한 경우에는 그 SQL도 함께 보인다.

기능이나 인스턴스 시나리오의 내용을 묻는 질의('이 기능은 무엇인가', '전원과 관련된 시나리오는 무엇인가')는 두 YAML 파일을 읽은 내용으로 답하며, SQL을 사용하지 않는다.

## 조회 스크립트가 오류로 종료한 경우

- 계산이 필요한 질의와 TC, 관계에 대한 질의에는 답하지 않는다. 오류의 내용과 필요한 조치만 사용자에게 알린다. 원본 파일을 직접 세어 대신 답하지 않는다.
- 변환 명령(`build.py`)을 실행하지 않는다. 오류 메시지의 마지막에 실행 줄이 있으면 그 줄을 고치지 않고 그대로 사용자에게 전달한다. 데이터베이스는 사용자가 그 줄을 실행할 때에만 만들어진다.
- 오류 메시지에 '데이터 폴더'의 경로가 있으면, 내용을 묻는 질의에는 그 폴더의 `features.yaml`과 `scenarios.yaml`을 읽고 답한다.
- 오류 메시지에 데이터 폴더의 경로가 없으면(환경 변수 `FTM_DATA_DIR`이 설정되지 않은 경우 등) 원본 파일을 찾지 않는다. 질의의 종류와 무관하게 오류의 내용만 사용자에게 알린다.

## 보고서를 요청받은 경우

사용자가 검증 공백을 화면이나 보고서로 보여 달라고 하면, 보고서 명령을 실행하지 않고 아래의 실행 줄을 안내한다. `<데이터 폴더>`에는 `schema` 명령의 출력에 있는 데이터 폴더의 절대 경로를, `<skill>`에는 이 폴더의 절대 경로를 넣는다. 보고서는 데이터 폴더의 `build/report.html`에 만들어지며, 브라우저로 연다.

```
python3 <skill>/report/report.py --data-dir "<데이터 폴더>"
```

Windows에서는 경로의 구분 문자를 `/`로 적고 `python3` 대신 `python`을 적는다. 조회 스크립트의 오류 메시지에 있는 실행 줄이 같은 표기를 쓴다.

## 스키마

정의의 원문은 `schema` 명령의 출력에 있다. 원본 파일의 키와 테이블의 열은 이름이 같다.

### 테이블

`feature`: 한 행이 기능 하나다.

| 열 | 의미 |
|---|---|
| `id` | 고유 ID |
| `name` | 이름 |
| `path` | 계층 경로. 최상위 항목부터 자신까지의 `name`을 ` > `로 이은 문자열이다. |
| `parent_id` | 부모 기능의 `id`. 최상위 항목은 NULL이다. |
| `description` | 자연어 설명 |
| `ims_ref` | IMS 원본 위치 |

`scenario`: 한 행이 인스턴스 시나리오 하나다. 인스턴스 시나리오는 기능을 자극, 환경, 응답, 응답 측정의 네 단계로 구체화한 시나리오이며, 말단 기능 하나에만 속한다.

| 열 | 의미 |
|---|---|
| `id` | 고유 ID. `<기능 ID>-S<번호>` 형식이다. 번호는 만든 순서일 뿐이며, 대표 시나리오와 같은 구분은 없다. |
| `feature_id` | 이 시나리오가 속한 기능의 `id` |
| `stimulus`, `environment`, `response`, `response_measure` | 자극, 환경, 응답, 응답 측정 |

`tc`: 한 행이 TC 하나다.

| 열 | 의미 |
|---|---|
| `id` | 고유 ID. 일련번호(정수)다. |
| `suite` | TC가 속한 suite 폴더의 경로 |
| `name` | TC 이름. suite 안에서 중복되지 않는다. |
| `source_file` | suite 폴더 안에서의 소스 코드 파일의 경로 |
| `owner` | TC를 운영하는 조직. `sv`는 검증 조직이 MTO 검증용으로 운영하는 TC이고, `sw-dev`는 개발 조직이 자체 검증에 사용하는 TC다. |
| `platform` | TC를 실행하는 환경. `msvp` 또는 `hapsim`(시뮬레이션)이다. |

`owner`와 `platform`은 TC의 분류다. 허용하는 값의 목록은 `v_tc_owner`와 `v_tc_platform`에 있으며, 두 열의 조합에는 제약이 없다.

`scenario_tc`: 한 행이 'TC 하나가 인스턴스 시나리오 하나를 검증한다'는 연결 하나다. 열은 `scenario_id`와 `tc_id`다.

`build_info`는 데이터베이스의 생성 정보이며, 질의에 답하는 데에는 사용하지 않는다.

### 데이터의 규칙

- 자식 항목이 없는 말단 기능이 검증 대상이다. 자식 항목을 가지는 기능은 묶음이며, 인스턴스 시나리오를 가지지 않는다.
- 모든 말단 기능은 인스턴스 시나리오를 하나 이상 가진다.
- 기능과 TC를 직접 잇는 테이블은 없다. TC가 검증하는 기능은 그 TC가 연결된 인스턴스 시나리오의 `feature_id`로 구한다.
- TC 하나가 여러 인스턴스 시나리오와 여러 기능에 연결될 수 있다. 따라서 기능별 TC 개수를 더한 값은 TC의 전체 개수와 다르다. TC의 전체 개수는 `tc` 테이블에서 센다.

### 뷰

| 뷰 | 한 행의 의미 | 열 |
|---|---|---|
| `v_leaf_feature` | 검증 대상인 말단 기능 하나 | `feature`와 같다. |
| `v_feature_subtree` | (`ancestor_id`, `feature_id`) 쌍 하나. `feature_id`는 `ancestor_id` 아래에 있는 말단 기능이다. 말단 기능 자신도 `ancestor_id = feature_id`인 행으로 포함한다. | `ancestor_id`, `feature_id` |
| `v_feature_tc` | (말단 기능, 그 기능을 검증하는 TC) 쌍 하나. 중복이 없다. | `feature_id`, `tc_id` |
| `v_scenario_tc_count` | 인스턴스 시나리오 하나 | `scenario_id`, `feature_id`, `tc_count` |
| `v_feature_tc_count` | 말단 기능 하나 | `feature_id`, `scenario_count`, `uncovered_scenario_count`, `tc_count` |
| `v_subtree_tc_count` | 기능 하나. 묶음 기능과 말단 기능을 모두 포함한다. | `feature_id`, `leaf_count`, `uncovered_leaf_count`, `tc_count` |
| `v_unlinked_tc` | 어느 인스턴스 시나리오에도 연결되지 않은 TC 하나 | `tc`와 같다. |
| `v_tc_owner`, `v_tc_platform` | `owner` 또는 `platform`에 허용하는 값 하나 | `owner` 또는 `platform` |
| `v_scenario_tc_count_by_owner`, `v_scenario_tc_count_by_platform` | (분류 값, 인스턴스 시나리오) 쌍 하나 | `owner` 또는 `platform`, `scenario_id`, `feature_id`, `tc_count` |
| `v_feature_tc_count_by_owner`, `v_feature_tc_count_by_platform` | (분류 값, 말단 기능) 쌍 하나 | `owner` 또는 `platform`, `feature_id`, `scenario_count`, `uncovered_scenario_count`, `tc_count` |
| `v_subtree_tc_count_by_owner`, `v_subtree_tc_count_by_platform` | (분류 값, 기능) 쌍 하나. 묶음 기능과 말단 기능을 모두 포함한다. | `owner` 또는 `platform`, `feature_id`, `leaf_count`, `uncovered_leaf_count`, `tc_count` |

- `tc_count`는 그 행의 대상에 연결된 TC의 수이며, 같은 TC는 한 번만 센다. 묶음 기능의 `tc_count`는 하위 기능의 `tc_count`를 더한 값이 아니라, 하위 기능의 TC를 모아 중복 없이 센 값이다.
- `uncovered`는 'TC가 하나도 연결되지 않았다'는 뜻이다. `uncovered_scenario_count`는 그 기능의 인스턴스 시나리오 중에서 TC가 없는 시나리오의 수이고, `uncovered_leaf_count`는 그 기능 아래의 말단 기능 중에서 TC가 없는 기능의 수다.
- `leaf_count`는 그 기능 아래에 있는 말단 기능의 수이며, 말단 기능 자신의 행에서는 1이다.
- 이름이 `_by_owner`와 `_by_platform`으로 끝나는 뷰는 TC의 분류별 집계다. 열의 의미는 이름의 앞부분이 같은 뷰와 같으며, 그 분류 값을 가진 TC만 센다. 이 뷰를 조회할 때에는 `WHERE owner = 'sv'`와 같이 분류 값을 반드시 지정한다. 지정하지 않으면 같은 기능이나 시나리오가 분류 값마다 한 행씩 나온다.
- 그 값을 가진 TC가 하나도 없는 분류 값도 분류별 집계 뷰에 행으로 나타나며, 이 경우에는 모든 기능의 `tc_count`가 0이다.

### 검증 공백

| 구하는 것 | 방법 |
|---|---|
| 인스턴스 시나리오 단위의 공백 | `v_scenario_tc_count`에서 `tc_count = 0`인 행 |
| 검증되지 않은 기능 | `v_feature_tc_count`에서 `tc_count = 0`인 행 |
| 묶음 기능 아래의 검증되지 않은 기능의 수 | `v_subtree_tc_count`에서 그 묶음의 `uncovered_leaf_count` |
| 운영 조직별 공백 | `v_scenario_tc_count_by_owner`, `v_feature_tc_count_by_owner`, `v_subtree_tc_count_by_owner`에서 `owner`를 지정하고 위와 같은 조건을 쓴다. |
| 실행 환경별 공백 | `v_scenario_tc_count_by_platform`, `v_feature_tc_count_by_platform`, `v_subtree_tc_count_by_platform`에서 `platform`을 지정하고 위와 같은 조건을 쓴다. |

기능에 TC가 연결되어 있어도 그 기능의 인스턴스 시나리오 중 일부에는 TC가 없을 수 있다. 검증 공백을 묻는 질의에는 기능 단위와 인스턴스 시나리오 단위를 구분하여 답한다.

질의가 운영 조직이나 실행 환경을 지정하면('MTO 검증에서 빠진 기능', 'sv가 검증하지 않는 시나리오', 'hapsim에서 검증하지 않는 기능') 분류별 집계 뷰를 사용한다. 지정하지 않으면 모든 TC를 기준으로 답하고, 응답에 그 기준을 밝힌다. 운영 조직과 실행 환경을 함께 지정한 질의는 뷰가 없으므로, `scenario_tc`와 `tc`를 조인하는 SQL을 작성하여 구한다.

## 질의 예시

아래의 ID는 예시다.

검증되지 않은 기능과, TC가 없는 인스턴스 시나리오:

```sql
SELECT feature_id FROM v_feature_tc_count WHERE tc_count = 0;
```

```sql
SELECT scenario_id, feature_id FROM v_scenario_tc_count WHERE tc_count = 0 ORDER BY scenario_id;
```

기능 `NS-CREATE`를 검증하는 TC의 목록:

```sql
SELECT t.id, t.suite, t.name
FROM v_feature_tc ft JOIN tc t ON t.id = ft.tc_id
WHERE ft.feature_id = 'NS-CREATE'
ORDER BY t.id;
```

묶음 기능 `NS`의 집계와, 그 아래의 말단 기능별 집계:

```sql
SELECT feature_id, leaf_count, uncovered_leaf_count, tc_count FROM v_subtree_tc_count WHERE feature_id = 'NS';
```

```sql
SELECT c.feature_id, c.scenario_count, c.uncovered_scenario_count, c.tc_count
FROM v_feature_subtree s JOIN v_feature_tc_count c ON c.feature_id = s.feature_id
WHERE s.ancestor_id = 'NS'
ORDER BY c.feature_id;
```

검증 조직(`sv`)의 TC로 검증되지 않는 기능과 인스턴스 시나리오:

```sql
SELECT feature_id FROM v_feature_tc_count_by_owner WHERE owner = 'sv' AND tc_count = 0 ORDER BY feature_id;
```

```sql
SELECT scenario_id, feature_id FROM v_scenario_tc_count_by_owner
WHERE owner = 'sv' AND tc_count = 0
ORDER BY scenario_id;
```

`sw-dev`가 `hapsim`에서 운영하는 TC로 검증되지 않는 인스턴스 시나리오(두 분류를 함께 지정한 경우):

```sql
SELECT s.id AS scenario_id, s.feature_id
FROM scenario s
WHERE NOT EXISTS (
  SELECT 1 FROM scenario_tc r JOIN tc t ON t.id = r.tc_id
  WHERE r.scenario_id = s.id AND t.owner = 'sw-dev' AND t.platform = 'hapsim')
ORDER BY s.id;
```

여러 기능을 함께 검증하는 TC:

```sql
SELECT t.id, t.suite, t.name, COUNT(*) AS feature_count
FROM v_feature_tc ft JOIN tc t ON t.id = ft.tc_id
GROUP BY t.id
HAVING COUNT(*) > 1
ORDER BY t.id;
```

검증 대상인 기능의 개수:

```sql
SELECT COUNT(*) AS leaf_count FROM v_leaf_feature;
```
