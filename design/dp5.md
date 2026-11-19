# DP-5 세부 설계: 실행 시점, 조회 절차, 질의 예시

> **상태: 일부 결정됨**
> 이 문서는 `DESIGN.md`의 DP-5에서 결정한 내용을 기능 레코드에 대하여 구체화한다. 2장의 '조회 스크립트가 오류로 종료한 경우'는 사용자가 결정하였으며 `DESIGN.md`의 DP-5에 반영하였다. 그 밖의 내용은 제안(미채택)이다. 사용자가 채택한 항목은 `DESIGN.md`의 DP-5에 반영하고, 이 문서에서는 제안 표시를 지운다.

## 범위

이 문서는 SQL이 작성되고 실행되는 시점, 데이터베이스가 만들어지는 시점, 에이전트가 질의에 답하는 절차를 다룬다. 테이블과 뷰의 정의는 [dp1.md](dp1.md)에, 변환은 [dp4.md](dp4.md)에, 조회 스크립트는 [dp6.md](dp6.md)에 있다.

## 1. 실행 시점

### SQL의 종류와 작성 시점

이 설계에서 SQL은 세 종류이며, 작성하는 주체와 시점이 서로 다르다.

| SQL | 작성하는 주체 | 작성 시점 | 실행 시점 |
|---|---|---|---|
| `CREATE TABLE`, `CREATE VIEW` | 개발자. 스킬 안의 정의 파일에 둔다([dp6.md](dp6.md)). | 구현할 때 | 변환할 때 |
| `INSERT` | 변환 명령. 원본의 레코드마다 실행한다. | 변환할 때 | 변환할 때 |
| `SELECT` | 에이전트(DP-5) | 질의에 답할 때 | 질의에 답할 때 |

에이전트는 `SELECT` 문만 작성한다. 테이블과 뷰를 만드는 SQL은 에이전트가 작성하지 않는다.

### 데이터베이스가 만들어지는 시점

데이터베이스의 테이블, 뷰, 레코드는 **사용자가 변환 명령을 실행할 때** 만들어진다. 사용자는 원본을 고친 뒤 변환 명령을 실행하여 데이터베이스를 미리 만들어 둔다. 만들어진 데이터베이스는 파일로 남으며, 원본이나 테이블 정의가 바뀔 때까지 그대로 사용한다.

질의에 답하는 과정에서는 데이터베이스를 만들지 않는다. 조회 스크립트는 데이터베이스가 없거나 오래되었으면 오류로 종료한다(DP-6).

### 질의의 종류

모든 질의가 SQL을 거치는 것은 아니다. 에이전트는 `features.yaml`을 전부 읽으므로(DP-5), 다음과 같이 나누어 처리한다.

| 질의의 종류 | 예 | 처리 방법 |
|---|---|---|
| 내용을 묻는 질의 | 'Sanitize는 어떤 기능인가', '전원과 관련된 기능은 무엇인가' | `features.yaml`만 읽고 답한다. 데이터베이스를 사용하지 않는다. |
| 세거나 모으는 질의 | '검증 대상인 기능은 몇 개인가', '`NS` 아래의 말단 기능은 무엇인가' | SQL로 구한다. |

기능 테이블만 있는 현재 범위에서는 두 번째 종류의 질의도 `features.yaml`만으로 답할 수 있다. 기능이 100개 미만이고 전체가 에이전트의 컨텍스트에 들어 있기 때문이다. SQL이 반드시 필요해지는 시점은 TC와 시나리오-TC 관계가 추가된 뒤다. 이 문서의 질의 예시는 그 전에 원본에서 SQL 조회까지의 경로를 테이블 하나로 확인하기 위한 것이다.

### 질의 하나가 처리되는 순서

1. 사용자가 에이전트에게 질의한다.
2. 에이전트가 `features.yaml`을 전부 읽고, 질의에 나오는 기능을 기능 ID로 바꾼다.
3. 내용을 묻는 질의이면 에이전트가 읽은 내용으로 답하고 끝낸다.
4. 계산이 필요한 질의이면 에이전트가 `SELECT` 문을 작성하여 조회 스크립트에 전달한다.
5. 조회 스크립트가 데이터베이스의 최신성을 검사한다. 데이터베이스가 없거나 오래되었으면 오류로 종료한다. 에이전트는 질의에 답하지 않고 변환 명령도 실행하지 않으며, 오류의 내용과 조회 스크립트가 출력한 실행 줄을 사용자에게 알린 뒤 끝낸다(2장).
6. 데이터베이스가 최신이면 조회 스크립트가 `SELECT` 문을 실행하고 결과를 에이전트에게 돌려준다.
7. 에이전트가 결과를 근거로 답한다.

## 2. 조회 절차

안내 문서(`SKILL.md`)는 에이전트에게 다음 절차를 지시한다.

1. `features.yaml`을 전부 읽는다.
2. 질의에 나오는 기능을 기능 ID로 바꾼다. 의미로 찾아야 하는 경우에는 `name`, `path`, `description`을 근거로 판단한다. 해당하는 기능이 여럿이면 모두 고른다.
3. 개수, 검증 대상 여부, 하위 트리처럼 계산이 필요한 질의는 `schema` 명령으로 테이블과 뷰를 확인한 뒤 SQL로 구한다. 가능하면 뷰를 사용한다.
4. 개수는 반드시 `COUNT`로 구하고, 결과 행을 세지 않는다. 조회 스크립트가 결과 행을 제한하므로([dp6.md](dp6.md)), 잘린 결과를 세면 개수가 틀린다.
5. 응답에 근거로 기능 ID를 인용한다. SQL을 실행한 경우에는 그 SQL도 함께 보인다.

2단계의 판단은 LLM이 하고, 3단계의 계산은 SQL이 한다. 의미로 찾는 질의와 집계 질의를 나누어 처리하는 DP-1의 논의를 절차로 옮긴 것이다.

### 조회 스크립트가 오류로 종료한 경우 (결정됨)

안내 문서는 위의 절차에 더하여 다음 규칙을 지시한다.

- 조회 스크립트가 오류로 종료하면, 계산이 필요한 질의에는 답하지 않고 오류의 내용과 필요한 조치만 사용자에게 알린다. `features.yaml`을 직접 세어 대신 답하지 않는다.
- 변환 명령을 직접 실행하지 않는다. 조회 스크립트가 출력한 실행 줄을 사용자에게 그대로 전달한다([dp6.md](dp6.md)).
- 내용을 묻는 질의는 데이터베이스를 사용하지 않으므로, 이 경우에도 `features.yaml`을 읽고 답한다.

기능 테이블만 있는 현재 범위에서는 에이전트가 `features.yaml`을 직접 세어도 답을 낼 수 있다(1장). 그러나 이를 허용하면 '계산은 SQL로 한다'는 규칙이 오류 상황에서만 지켜지지 않고, TC가 추가된 뒤에는 쓸 수 없는 방법이 절차에 남는다. 따라서 오류 상황에서도 직접 세지 않는다.

## 3. 질의 예시

아래 결과는 `examples/features.yaml`의 **예시 데이터**로 만든 데이터베이스에서 실제로 실행한 결과다. [dp1.md](dp1.md)의 테이블 정의와 뷰를 그대로 사용하였다. 확인에 사용한 스크립트는 시험용이므로 저장소에 포함하지 않았다.

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

## 4. 사용자의 결정이 필요한 사항

- 2장의 조회 절차를 채택할지 정한다.
