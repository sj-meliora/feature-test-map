# DP-1 세부 설계: 기능 레코드의 항목 이름, 테이블, 뷰

> **상태: 결정됨**
> 이 문서는 `DESIGN.md`의 DP-1에서 결정한 내용을 구체화한다. 문서의 내용은 사용자가 채택하였으며 `DESIGN.md`의 DP-1에 반영하였다. 5장의 '미결'에 적은 항목은 제외한다.

## 범위

이 문서는 기능 레코드의 항목 이름과 자료형, 데이터베이스의 테이블 정의, 뷰를 다룬다. 인스턴스 시나리오, TC, 시나리오-TC 관계는 다루지 않으며, 기능 레코드의 경로가 정해진 뒤에 같은 틀로 추가한다.

관련 문서는 다음과 같다.

| 문서 | 내용 |
|---|---|
| [dp4.md](dp4.md) | 원본 파일(`features.yaml`)의 형식, 변환 절차, 검증 규칙 |
| [dp5.md](dp5.md) | SQL이 작성되고 실행되는 시점, 에이전트의 조회 절차, 질의 예시 |
| [dp6.md](dp6.md) | 조회 스크립트, 최신성 검사, 읽기 전용의 보장 |

## 1. 항목의 영문 이름

기능 레코드의 항목의 영문 이름과 자료형은 다음과 같다. 같은 이름을 YAML 파일의 키와 데이터베이스의 열 이름에 함께 사용한다.

| 항목 | 영문 이름 | 자료형 |
|---|---|---|
| 고유 ID | `id` | TEXT |
| 이름 | `name` | TEXT |
| 계층 경로 | `path` | TEXT |
| 부모 ID | `parent_id` | TEXT, NULL 허용 |
| 자연어 설명 | `description` | TEXT |
| IMS 원본 위치 | `ims_ref` | TEXT |

테이블 이름은 `feature`로 한다. 에이전트가 `feature.id`와 같이 '테이블 이름.열 이름'으로 읽을 때 자연스럽도록 단수형으로 둔다.

## 2. 테이블 정의

```sql
CREATE TABLE feature (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  path        TEXT NOT NULL,
  parent_id   TEXT REFERENCES feature(id) DEFERRABLE INITIALLY DEFERRED,
  description TEXT NOT NULL,
  ims_ref     TEXT NOT NULL
);
```

`parent_id`의 외래 키는 검사를 트랜잭션이 끝나는 시점으로 미룬다(`DEFERRABLE INITIALLY DEFERRED`). SQLite는 기본적으로 외래 키를 문장마다 검사하므로, 미루지 않으면 원본에서 자식 항목이 부모 항목보다 먼저 적힌 경우에 삽입이 실패한다. 검사를 미루면 원본에 적힌 순서와 무관하게 레코드를 넣을 수 있고, 존재하지 않는 부모를 가리키는 레코드는 커밋 시점에 거부된다.

## 3. 뷰

검증 대상의 판정(자식 항목이 없는 기능)과 하위 트리의 탐색(재귀 질의)은 에이전트가 매번 작성하면 틀리기 쉬우므로 뷰로 정의한다(DP-5).

| 뷰 | 한 행의 의미 | 쓰는 경우 |
|---|---|---|
| `v_leaf_feature` | 검증 대상인 말단 기능 하나 | 검증 대상만 다룰 때 |
| `v_feature_subtree` | (상위 기능, 그 아래의 말단 기능) 쌍 하나 | 묶음 단위로 말단 기능을 모을 때 |

```sql
CREATE VIEW v_leaf_feature AS
SELECT f.*
FROM feature f
WHERE NOT EXISTS (SELECT 1 FROM feature c WHERE c.parent_id = f.id);

CREATE VIEW v_feature_subtree AS
WITH RECURSIVE sub(ancestor_id, feature_id) AS (
  SELECT id, id FROM feature
  UNION ALL
  SELECT sub.ancestor_id, c.id
  FROM sub JOIN feature c ON c.parent_id = sub.feature_id
)
SELECT sub.ancestor_id, sub.feature_id
FROM sub JOIN v_leaf_feature l ON l.id = sub.feature_id;
```

- `v_leaf_feature`는 DP-1의 '검증 대상인지는 자식 항목의 유무로 판단한다'를 그대로 옮긴 것이다. 구분 항목을 따로 두지 않는다는 결정을 유지하면서, 판정 방법은 한 곳에만 둔다.
- `v_feature_subtree`는 말단 기능 자신도 `ancestor_id = feature_id`인 행으로 포함한다. 따라서 묶음 기능과 말단 기능을 같은 질의로 다룰 수 있다.
- 이후 TC와 관계가 추가되면, '상위 항목의 결과는 하위 항목의 결과를 합하여 구한다'(DP-1)는 `v_feature_subtree`에 기능별 집계를 조인하여 계산한다.

## 4. 논의

### 원본의 키 이름과 열 이름을 같게 할지

원본은 한국어 키로 쓰고 데이터베이스에서 영문 열 이름으로 바꾸는 안도 있다. 원본을 사람이 읽기는 쉬워지지만, 변환 단계에 이름 대응표가 생기고 에이전트가 같은 항목을 두 이름으로 보게 된다. 원본의 주석에 한국어 설명을 적어 두는 것으로 가독성을 보완하고, 이름은 하나로 통일하는 안을 채택하였다.

### 원본에 적힌 순서와 외래 키 검사

| 설계안 | 얻는 것 | 잃는 것 |
|---|---|---|
| 외래 키 검사를 트랜잭션 끝으로 미룸 (채택) | 원본에 레코드를 적는 순서가 자유롭다. | 테이블 정의에 `DEFERRABLE` 구문이 추가된다. |
| '부모 항목이 자식 항목보다 먼저 나온다'를 검증 규칙에 추가 | 원본 파일이 항상 트리 순서로 읽힌다. | 사람이 순서를 지켜야 하며, 어기면 변환이 실패한다. |

순서는 데이터의 의미에 영향을 주지 않으므로, 사람이 지켜야 할 규칙을 늘리지 않는 첫 번째 안을 채택하였다.

## 5. 미결

- 형제 항목의 `name`이 같으면 `path`도 같아진다. `path`가 중복되지 않아야 한다는 규칙을 둘지 정해야 한다. 이 항목은 실제 IMS structure에 이름이 같은 형제 항목이 있는지 확인한 뒤에 정한다.
