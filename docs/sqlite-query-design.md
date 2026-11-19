# 기능 레코드의 SQLite 변환과 에이전트 조회 설계안

> **상태: 제안(미채택)**
> 이 문서는 DP-1(기능 레코드), DP-4(원본 형식), DP-5(LLM의 조회 방식), DP-6(에이전트 접점)에서 결정한 내용을 기능 레코드에 대하여 구체화하는 제안이다. 사용자가 채택한 항목은 `DESIGN.md`에 DP로 옮기고, 이 문서에서는 제안 표시를 지운다.

## 범위

이 문서는 **기능 레코드만** 다룬다. 원본 YAML 파일에서 SQLite 데이터베이스를 만들고, 에이전트가 SQL로 조회하기까지의 경로를 테이블 하나로 먼저 정한다. 인스턴스 시나리오, TC, 시나리오-TC 관계는 이 경로가 정해진 뒤에 같은 틀로 추가한다.

DP-5에 따라 에이전트는 기능 목록을 전부 읽는다. 따라서 기능 테이블에 대한 SQL 조회는 의미로 찾는 질의가 아니라, 말단 기능의 판정, 하위 트리의 탐색, 개수의 집계와 같은 구조 질의에 사용한다. 이후 TC와 관계가 추가되면, 이 문서에서 정한 뷰가 기능 단위 집계의 기반이 된다.

`examples/features.yaml`의 예시 데이터로 스키마와 뷰를 만들고 질의 예시를 실행하여, 이 문서에 적은 SQL과 결과가 실제로 동작함을 확인하였다. 확인에 사용한 스크립트는 시험용이므로 저장소에 포함하지 않았다.

## 1. 항목의 영문 이름

`DESIGN.md`에서 미결로 둔 '항목의 영문 이름'을 기능 레코드에 대하여 다음과 같이 제안한다. 같은 이름을 YAML 파일의 키와 데이터베이스의 열 이름에 함께 사용한다. 이름이 같으면 변환 과정에서 이름을 바꾸는 단계가 없고, 에이전트가 YAML 파일과 SQL 결과를 같은 이름으로 대조할 수 있다.

| 항목 | 영문 이름 | 자료형 |
|---|---|---|
| 고유 ID | `id` | TEXT |
| 이름 | `name` | TEXT |
| 계층 경로 | `path` | TEXT |
| 부모 ID | `parent_id` | TEXT, NULL 허용 |
| 자연어 설명 | `description` | TEXT |
| IMS 원본 위치 | `ims_ref` | TEXT |

테이블 이름은 `feature`로 한다. 에이전트가 `feature.id`와 같이 '테이블 이름.열 이름'으로 읽을 때 자연스럽도록 단수형으로 둔다.

## 2. 원본 파일

기능 레코드의 원본은 데이터 폴더의 `features.yaml` 하나다. 파일은 레코드의 목록 하나로 구성한다. 트리로 중첩하지 않고 평면 목록으로 적으며(DP-1), 계층은 `parent_id`와 `path`로 나타낸다.

```yaml
# 예시
- id: NS
  name: Namespace Management
  path: Namespace Management
  parent_id: null
  description: >-
    호스트가 namespace를 생성하고 삭제하는 기능의 묶음이다.
  ims_ref: IMS-EX-0100

- id: NS-CREATE
  name: Namespace Create
  path: Namespace Management > Namespace Create
  parent_id: NS
  description: >-
    Namespace Management 커맨드(Create)로 미할당 용량에서 새 namespace를
    만들고 NSID를 할당한다. 용량이 부족하거나 namespace 수가 최대에
    도달하면 오류로 완료한다.
  ims_ref: IMS-EX-0101
```

- `path`는 루트부터 자신까지의 `name`을 ` > `로 이은 문자열이다. `parent_id`에서 계산할 수 있는 값이지만, 에이전트가 YAML 파일을 그대로 읽으므로(DP-5) 원본에 적는다. 두 값이 어긋나면 변환 단계에서 오류로 처리한다.
- 최상위 항목은 `parent_id`를 `null`로 적는다. 키를 생략하지 않고 값을 명시하여, 키를 빠뜨린 실수와 구분한다.
- 긴 설명은 `>-` 블록으로 적는다. 여러 줄로 적어도 한 줄의 문장으로 읽힌다.
- 파일 머리의 주석에 각 키의 의미를 적어, 사람이 파일만 열어도 항목을 알 수 있게 한다.

## 3. 변환

### 절차

변환 명령은 데이터 폴더를 입력받아 SQLite 파일 하나를 만든다. 원본이 작으므로(기능 100개 미만) 매번 데이터베이스 전체를 새로 만들며, 변경분만 반영하는 방식은 사용하지 않는다.

1. `features.yaml`을 읽는다.
2. 아래의 '검증 규칙'으로 원본을 검사한다. 오류가 하나라도 있으면 데이터베이스를 만들지 않고, 발견한 오류를 모두 출력한 뒤 종료한다.
3. 임시 파일에 스키마와 뷰를 만들고 레코드를 넣는다. 외래 키 검사(`PRAGMA foreign_keys = ON`)를 켠다.
4. `build_info` 테이블에 원본 파일의 해시와 생성 시각을 기록한다.
5. 임시 파일을 최종 경로로 옮긴다. 옮기기는 원자적으로 수행되므로, 조회 중에 반쯤 만들어진 데이터베이스를 읽는 일이 없다.

### 검증 규칙

스키마의 제약(기본 키, 외래 키, `NOT NULL`)으로 잡을 수 있는 오류는 SQLite가 잡는다. 그러나 SQLite는 첫 번째 오류에서 멈추고 원본의 어느 레코드인지 알려 주지 않으므로, 변환 명령이 넣기 전에 먼저 검사하여 레코드 ID와 함께 모든 오류를 출력한다.

| 규칙 | 근거 |
|---|---|
| 여섯 개의 키가 모두 있다. `parent_id`를 제외한 값은 비어 있지 않다. 정의되지 않은 키가 없다. | 키의 오타와 누락을 잡는다. |
| `id`가 중복되지 않는다. | 기본 키 |
| `parent_id`가 있으면 그 기능이 존재한다. | 외래 키 |
| 부모를 따라 올라갔을 때 순환하지 않는다. | 순환하면 계층 경로와 하위 트리가 정의되지 않는다. |
| `path`가 부모의 `path`에 ` > `와 자신의 `name`을 붙인 값과 같다. 최상위 항목은 `path`가 `name`과 같다. | 2장 |

### 스키마

```sql
CREATE TABLE feature (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  path        TEXT NOT NULL,
  parent_id   TEXT REFERENCES feature(id),
  description TEXT NOT NULL,
  ims_ref     TEXT NOT NULL
);

CREATE TABLE build_info (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

`build_info`는 데이터가 아닌 생성 정보를 담는다. 4장의 최신성 검사에 사용한다.

### 뷰

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

## 4. 데이터베이스의 위치와 최신성

데이터베이스 파일은 데이터 폴더 아래의 `build/ftm.db`에 만들고, `build/`는 git에서 제외한다. 데이터베이스는 원본에서 언제든 다시 만들 수 있는 파일이므로 저장소에 넣지 않는다.

원본을 고친 뒤 변환하지 않으면, 에이전트가 이전 데이터로 답하게 된다. 이를 막기 위하여 조회 스크립트는 질의를 실행하기 전에 원본 파일의 해시를 `build_info`에 기록된 해시와 비교한다. 해시가 다르거나 데이터베이스가 없으면, 변환을 먼저 실행한 뒤 질의를 실행한다.

이 방식에서 조회 스크립트는 데이터베이스 파일을 다시 만들 수 있지만, 원본 파일은 바꾸지 않는다. DP-6의 '읽기 전용'은 원본 데이터를 바꾸지 않는다는 뜻으로 해석한다.

## 5. 에이전트의 조회

### 조회 스크립트

스킬(DP-6)은 조회 스크립트 하나를 포함하며, 하위 명령 두 개를 제공한다.

| 명령 | 동작 |
|---|---|
| `schema` | 테이블과 뷰의 정의, 테이블별 레코드 수, 생성 시각을 출력한다. |
| `sql "<SELECT 문>"` | SQL 한 문장을 실행하고 결과를 표로 출력한다. |

데이터 폴더의 경로는 설정으로 전달받는다(DP-6). 기능 목록은 에이전트가 `features.yaml`을 직접 읽으므로(DP-5), 조회 스크립트에는 이를 출력하는 명령을 두지 않는다.

### 읽기 전용의 보장

조회 스크립트는 다음 세 겹으로 쓰기를 막는다.

1. 데이터베이스를 읽기 전용 모드로 연다(`file:...?mode=ro`).
2. `PRAGMA query_only = ON`을 설정한다.
3. SQLite의 권한 확인 콜백(authorizer)에서 읽기, 선택, 함수 호출, 재귀 질의만 허용한다. `ATTACH`, `PRAGMA`, 쓰기 문은 실행 전에 거부된다.

시험용 스크립트에서 `DELETE`, `ATTACH`, `PRAGMA writable_schema = 1`이 모두 `not authorized`로 거부됨을 확인하였다.

### 결과 행의 제한

결과가 지나치게 길면 에이전트의 컨텍스트를 차지하므로, 출력하는 행을 200행으로 제한하고, 제한을 넘으면 잘렸다는 표시를 출력한다. 기능은 100개 미만이므로 기능 테이블만 있는 지금은 제한에 걸리지 않으나, TC가 추가되면 필요해진다.

잘린 결과를 에이전트가 세면 개수가 틀린다. 따라서 안내 문서에 '개수는 반드시 `COUNT`로 구하고, 결과 행을 세지 않는다'는 규칙을 둔다.

### 조회 절차

안내 문서(`SKILL.md`)는 에이전트에게 다음 절차를 지시한다.

1. `features.yaml`을 전부 읽는다.
2. 질의에 나오는 기능을 기능 ID로 바꾼다. 의미로 찾아야 하는 경우에는 `name`, `path`, `description`을 근거로 판단한다. 해당하는 기능이 여럿이면 모두 고른다.
3. 개수, 검증 대상 여부, 하위 트리처럼 계산이 필요한 질의는 `schema`로 테이블과 뷰를 확인한 뒤 SQL로 구한다. 가능하면 뷰를 사용한다.
4. 응답에 근거로 기능 ID를 인용한다. SQL을 실행한 경우에는 그 SQL도 함께 보인다.

2단계의 판단은 LLM이 하고, 3단계의 계산은 SQL이 한다. 의미로 찾는 질의와 집계 질의를 나누어 처리하는 DP-1의 논의를 절차로 옮긴 것이다.

## 6. 질의 예시

아래 결과는 `examples/features.yaml`의 **예시 데이터**로 만든 데이터베이스에서 실제로 실행한 결과다.

### 검증 대상인 기능은 몇 개인가

```sql
SELECT COUNT(*) AS leaf_count FROM v_leaf_feature;
```

| leaf_count |
|---|
| 7 |

전체 기능은 8개이지만, 묶음인 `NS`는 검증 대상이 아니므로 7개다.

### 검증 대상인 기능의 목록

```sql
SELECT id, name, path FROM v_leaf_feature ORDER BY path;
```

| id | name | path |
|---|---|---|
| FLUSH | Flush | Flush |
| FORMAT | Format NVM | Format NVM |
| NS-CREATE | Namespace Create | Namespace Management > Namespace Create |
| NS-DELETE | Namespace Delete | Namespace Management > Namespace Delete |
| PS-TRANSITION | Power State Transition | Power State Transition |
| SANITIZE | Sanitize | Sanitize |
| SPOR | Sudden Power-Off Recovery | Sudden Power-Off Recovery |

### namespace 관련 기능 중 검증 대상은 무엇인가

에이전트는 `features.yaml`을 읽고 'namespace 관련 기능'을 묶음 기능 `NS`로 바꾼 뒤 다음 SQL을 작성한다.

```sql
SELECT f.id, f.name
FROM v_feature_subtree s
JOIN feature f ON f.id = s.feature_id
WHERE s.ancestor_id = 'NS'
ORDER BY f.id;
```

| id | name |
|---|---|
| NS-CREATE | Namespace Create |
| NS-DELETE | Namespace Delete |

### 묶음 기능마다 검증 대상은 몇 개인가

```sql
SELECT g.id, g.name, COUNT(*) AS leaf_count
FROM feature g
JOIN v_feature_subtree s ON s.ancestor_id = g.id
WHERE g.id NOT IN (SELECT id FROM v_leaf_feature)
GROUP BY g.id;
```

| id | name | leaf_count |
|---|---|---|
| NS | Namespace Management | 2 |

### IMS의 특정 항목은 어느 기능인가

```sql
SELECT id, name, ims_ref FROM feature WHERE ims_ref = 'IMS-EX-0300';
```

| id | name | ims_ref |
|---|---|---|
| SANITIZE | Sanitize | IMS-EX-0300 |

## 7. 논의

### 데이터베이스를 파일로 둘지, 질의마다 메모리에 만들지

| 설계안 | 얻는 것 | 잃는 것 |
|---|---|---|
| 파일로 두고 해시로 최신성 검사 (제안) | 시각화(FR-4)나 DB 도구가 같은 파일을 열 수 있다. 질의마다 원본을 해석하지 않는다. | 최신성 검사와 원자적 교체를 구현해야 한다. |
| 질의마다 원본을 읽어 메모리에 생성 | 최신성 문제가 원천적으로 없다. 파일을 쓰지 않으므로 읽기 전용이 자명하다. | 질의마다 원본 해석과 검증을 반복한다. 다른 도구와 데이터베이스를 공유할 수 없다. |

원본의 규모에서는 두 번째 안의 비용도 크지 않다. 그러나 전체 구조도(`docs/architecture.html`)가 'DB 생성'과 '조회용 SQLite DB'를 별도의 요소로 두고 있고, 시각화도 같은 데이터베이스를 사용할 수 있으므로 첫 번째 안을 제안한다. 첫 번째 안의 단점인 최신성 문제는 해시 비교로 해소한다.

### 오래된 데이터베이스를 발견했을 때

| 설계안 | 얻는 것 | 잃는 것 |
|---|---|---|
| 조회 스크립트가 다시 변환한 뒤 질의 (제안) | 에이전트가 이전 데이터로 답하는 일이 없다. 사용자가 변환을 신경 쓰지 않아도 된다. | 조회 스크립트가 데이터베이스 파일을 쓴다. 원본에 오류가 있으면 질의가 실패한다. |
| 경고만 출력하고 기존 데이터베이스로 질의 | 조회 스크립트가 아무 파일도 쓰지 않는다. | 에이전트가 경고를 무시하면 이전 데이터로 답한다. |

원본에 오류가 있어 변환이 실패하면 질의도 실패하는데, 이는 잘못된 데이터로 답하는 것보다 낫다고 판단하여 첫 번째 안을 제안한다.

### 원본의 키 이름과 열 이름을 같게 할지

원본은 한국어 키로 쓰고 데이터베이스에서 영문 열 이름으로 바꾸는 안도 있다. 원본을 사람이 읽기는 쉬워지지만, 변환 단계에 이름 대응표가 생기고 에이전트가 같은 항목을 두 이름으로 보게 된다. 원본의 주석에 한국어 설명을 적어 두는 것으로 가독성을 보완하고, 이름은 하나로 통일하는 안을 제안한다.

## 8. 사용자의 결정이 필요한 사항

- 1장의 영문 이름과 자료형, 3장의 뷰 이름과 구성을 채택할지 정한다.
- 4장의 데이터베이스 위치와, 오래된 데이터베이스를 발견했을 때 다시 변환하는 동작을 채택할지 정한다.
- 결과 행의 제한(200행)이 적절한지 정한다.
- 채택한 뒤에는 `DESIGN.md`에 DP로 옮기고, `docs/record-relations.html`의 항목 이름을 함께 고친다.
