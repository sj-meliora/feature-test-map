---
name: ftm-query
description: Feature-Test Map의 데이터(SSD FW의 기능 목록)를 읽기 전용으로 조회한다. 기능의 내용, 기능의 개수, 검증 대상인 기능, 묶음 기능 아래의 하위 기능, IMS 항목과 기능의 대응에 대한 질의에 답할 때 사용한다.
---

# ftm-query

Feature-Test Map의 데이터를 조회하여 질의에 답하는 절차다. 현재 데이터에는 기능 레코드만 있다.

## 명령

아래에서 `<skill>`은 이 `SKILL.md`가 있는 폴더의 경로다.

| 명령 | 동작 |
|---|---|
| `python3 <skill>/scripts/query.py schema` | 데이터 폴더의 절대 경로, 테이블과 뷰의 정의, 테이블별 레코드 수, 생성 시각을 출력한다. |
| `python3 <skill>/scripts/query.py sql "<SELECT 문>"` | SELECT 문 한 문장을 실행하고 결과를 표로 출력한다. |

조회 스크립트는 읽기 전용이다. SELECT 문 이외의 문장은 거부된다.

## 조회 절차

1. `schema` 명령을 실행하여 데이터 폴더의 경로와 테이블, 뷰의 정의를 확인한다. 데이터 폴더의 경로는 이 출력에서만 얻으며, 환경 변수를 직접 읽거나 경로를 추측하지 않는다.
2. 출력의 '기능 원본'에 적힌 `features.yaml`을 처음부터 끝까지 전부 읽는다.
3. 질의에 나오는 기능을 기능 ID로 바꾼다. 의미로 찾아야 하는 경우에는 `name`, `path`, `description`을 근거로 판단한다. 해당하는 기능이 여럿이면 모두 고른다.
4. 개수, 검증 대상 여부, 하위 트리처럼 계산이 필요한 질의는 `sql` 명령으로 구한다. 가능하면 뷰를 사용한다.
5. 개수는 반드시 `COUNT`로 구하고, 결과 행을 세지 않는다. 조회 스크립트는 결과를 200행까지만 출력하므로, 잘린 결과를 세면 개수가 틀린다.
6. 응답에 근거로 기능 ID를 인용한다. SQL을 실행한 경우에는 그 SQL도 함께 보인다.

기능의 내용을 묻는 질의('이 기능은 무엇인가', '전원과 관련된 기능은 무엇인가')는 `features.yaml`을 읽은 내용으로 답하며, SQL을 사용하지 않는다.

## 조회 스크립트가 오류로 종료한 경우

- 계산이 필요한 질의에는 답하지 않는다. 오류의 내용과 필요한 조치만 사용자에게 알린다. `features.yaml`을 직접 세어 대신 답하지 않는다.
- 변환 명령(`build.py`)을 실행하지 않는다. 오류 메시지의 마지막에 실행 줄이 있으면 그 줄을 고치지 않고 그대로 사용자에게 전달한다. 데이터베이스는 사용자가 그 줄을 실행할 때에만 만들어진다.
- 오류 메시지에 '데이터 폴더'의 경로가 있으면, 내용을 묻는 질의에는 그 폴더의 `features.yaml`을 읽고 답한다.
- 오류 메시지에 데이터 폴더의 경로가 없으면(환경 변수 `FTM_DATA_DIR`이 설정되지 않은 경우 등) `features.yaml`을 찾지 않는다. 질의의 종류와 무관하게 오류의 내용만 사용자에게 알린다.

## 스키마

정의의 원문은 `schema` 명령의 출력에 있다. `features.yaml`의 키와 `feature` 테이블의 열은 이름이 같다.

### 테이블 `feature`

한 행이 기능 하나다.

| 열 | 의미 |
|---|---|
| `id` | 고유 ID. 응답에서 근거로 인용한다. |
| `name` | 이름 |
| `path` | 계층 경로. 최상위 항목부터 자신까지의 `name`을 ` > `로 이은 문자열이다. |
| `parent_id` | 부모 기능의 `id`. 최상위 항목은 NULL이다. |
| `description` | 자연어 설명 |
| `ims_ref` | IMS 원본 위치 |

자식 항목이 없는 말단 기능이 검증 대상이다. 자식 항목을 가지는 기능은 묶음이며 검증 대상이 아니다. 검증 대상인지를 나타내는 열은 없으므로, 아래의 뷰로 판정한다.

### 뷰

| 뷰 | 한 행의 의미 | 쓰는 경우 |
|---|---|---|
| `v_leaf_feature` | 검증 대상인 말단 기능 하나. 열은 `feature`와 같다. | 검증 대상만 다룰 때 |
| `v_feature_subtree` | (`ancestor_id`, `feature_id`) 쌍 하나. `feature_id`는 `ancestor_id` 아래에 있는 말단 기능이다. 말단 기능 자신도 `ancestor_id = feature_id`인 행으로 포함한다. | 묶음 기능 아래의 말단 기능을 모을 때 |

### 테이블 `build_info`

데이터베이스의 생성 정보다. 질의에 답하는 데에는 사용하지 않는다.

## 질의 예시

검증 대상인 기능의 개수:

```sql
SELECT COUNT(*) AS leaf_count FROM v_leaf_feature;
```

묶음 기능 `NS` 아래의 검증 대상(`NS`는 예시 ID다):

```sql
SELECT f.id, f.name
FROM v_feature_subtree s
JOIN feature f ON f.id = s.feature_id
WHERE s.ancestor_id = 'NS'
ORDER BY f.id;
```

묶음 기능마다 검증 대상의 개수:

```sql
SELECT g.id, g.name, COUNT(*) AS leaf_count
FROM feature g
JOIN v_feature_subtree s ON s.ancestor_id = g.id
WHERE g.id NOT IN (SELECT id FROM v_leaf_feature)
GROUP BY g.id;
```
