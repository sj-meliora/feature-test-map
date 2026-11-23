# DP-5 세부 설계: 실행 시점, 조회 절차, 질의 예시

> **상태: 결정됨**
> 이 문서는 `DESIGN.md`의 DP-5에서 결정한 내용을 기능 레코드에 대하여 구체화한다. 문서의 내용은 사용자가 채택하였으며 `DESIGN.md`의 DP-5에 반영하였다.

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

모든 질의가 SQL을 거치는 것은 아니다. 에이전트는 `features.yaml`과 `scenarios.yaml`을 전부 읽으므로(DP-5), 다음과 같이 나누어 처리한다.

| 질의의 종류 | 예 | 처리 방법 |
|---|---|---|
| 내용을 묻는 질의 | 'Sanitize는 어떤 기능인가', '전원과 관련된 기능은 무엇인가', 'Sanitize에는 어떤 시나리오가 있는가' | 두 YAML 파일만 읽고 답한다. 데이터베이스를 사용하지 않는다. |
| 세거나 모으는 질의 | '검증 대상인 기능은 몇 개인가', '`NS` 아래의 말단 기능은 무엇인가' | SQL로 구한다. |

기능에 대한 질의 가운데 일부는 두 번째 종류이더라도 `features.yaml`만으로 답할 수 있다. 기능이 100개 미만이고 전체가 에이전트의 컨텍스트에 들어 있기 때문이다. 그러나 TC와 관계는 에이전트가 읽지 않으므로, TC가 관련된 질의는 SQL 없이 답할 수 없다. 절차를 하나로 유지하기 위하여, 계산이 필요한 질의는 대상과 무관하게 SQL로 구한다.

### 질의 하나가 처리되는 순서

1. 사용자가 에이전트에게 질의한다.
2. 에이전트가 조회 스크립트의 `schema` 명령을 실행한다. 조회 스크립트는 데이터베이스의 최신성을 검사한 뒤, 데이터 폴더의 절대 경로와 테이블, 뷰의 정의를 출력한다. 데이터베이스가 없거나 오래되었으면 오류로 종료하며, 이 오류 메시지에도 데이터 폴더의 절대 경로가 포함된다([dp6.md](dp6.md)).
3. 에이전트가 그 경로의 `features.yaml`과 `scenarios.yaml`을 전부 읽고, 질의에 나오는 기능과 인스턴스 시나리오를 ID로 바꾼다.
4. 내용을 묻는 질의이면 에이전트가 읽은 내용으로 답하고 끝낸다. 2단계가 최신성 검사의 오류로 종료한 경우에도 같다.
5. 계산이 필요한 질의인데 2단계가 오류로 종료하였으면, 에이전트는 질의에 답하지 않고 변환 명령도 실행하지 않으며, 오류의 내용과 조회 스크립트가 출력한 실행 줄을 사용자에게 알린 뒤 끝낸다(2장).
6. 계산이 필요한 질의이면 에이전트가 `SELECT` 문을 작성하여 조회 스크립트의 `sql` 명령에 전달한다. 조회 스크립트는 최신성을 다시 검사한 뒤 `SELECT` 문을 실행하고 결과를 에이전트에게 돌려준다.
7. 에이전트가 결과를 근거로 답한다.

환경 변수 `FTM_DATA_DIR`이 설정되지 않은 경우에는 조회 스크립트가 데이터 폴더의 경로를 알 수 없으므로, 2단계의 오류 메시지에 경로가 없다. 이 경우 에이전트는 `features.yaml`을 읽을 수 없으며, 질의의 종류와 무관하게 오류의 내용만 사용자에게 알린다.

## 2. 조회 절차

안내 문서(`SKILL.md`)는 에이전트에게 다음 절차를 지시한다.

1. 조회 스크립트의 `schema` 명령을 실행하여 데이터 폴더의 경로와 테이블, 뷰의 정의를 확인한다.
2. 그 경로의 `features.yaml`과 `scenarios.yaml`을 전부 읽는다.
3. 질의에 나오는 기능과 인스턴스 시나리오를 ID로 바꾼다. 의미로 찾아야 하는 경우에는 기능의 `name`, `path`, `description`과 인스턴스 시나리오의 단계별 내용을 근거로 판단한다. 해당하는 대상이 여럿이면 모두 고른다.
4. TC와 관계에 대한 질의, 그리고 개수, 검증 대상 여부, 하위 트리처럼 계산이 필요한 질의는 SQL로 구한다. 가능하면 뷰를 사용한다. TC와 관계의 원본 파일은 읽지 않는다.
5. 개수는 반드시 `COUNT`로 구하고, 결과 행을 세지 않는다. 조회 스크립트가 결과 행을 제한하므로([dp6.md](dp6.md)), 잘린 결과를 세면 개수가 틀린다.
6. 응답에 근거로 기능 ID, 인스턴스 시나리오 ID, TC의 ID와 이름을 인용한다. SQL을 실행한 경우에는 그 SQL도 함께 보인다.

`schema`를 가장 먼저 실행하는 이유는, 에이전트가 데이터 폴더의 경로를 조회 스크립트의 출력에서 얻기 때문이다(DP-6). 에이전트가 환경 변수를 따로 해석하지 않으므로, 조회 스크립트가 사용한 경로와 에이전트가 읽은 경로가 어긋나지 않는다.

3단계의 판단은 LLM이 하고, 4단계의 계산은 SQL이 한다. 의미로 찾는 질의와 집계 질의를 나누어 처리하는 DP-1의 논의를 절차로 옮긴 것이다.

### 조회 스크립트가 오류로 종료한 경우

안내 문서는 위의 절차에 더하여 다음 규칙을 지시한다.

- 조회 스크립트가 오류로 종료하면, 계산이 필요한 질의와 TC, 관계에 대한 질의에는 답하지 않고 오류의 내용과 필요한 조치만 사용자에게 알린다. 원본 파일을 직접 세어 대신 답하지 않는다.
- 변환 명령을 직접 실행하지 않는다. 조회 스크립트가 출력한 실행 줄을 사용자에게 그대로 전달한다([dp6.md](dp6.md)).
- 내용을 묻는 질의는 데이터베이스를 사용하지 않으므로, 이 경우에도 오류 메시지에 적힌 데이터 폴더의 `features.yaml`과 `scenarios.yaml`을 읽고 답한다.

기능의 개수와 같은 일부 질의는 에이전트가 `features.yaml`을 직접 세어도 답을 낼 수 있다(1장). 그러나 이를 허용하면 '계산은 SQL로 한다'는 규칙이 오류 상황에서만 지켜지지 않고, TC가 관련된 질의에는 쓸 수 없는 방법이 절차에 남는다. 따라서 오류 상황에서도 직접 세지 않는다.

## 3. 집계 뷰

기능, 인스턴스 시나리오, 관계를 조인하는 집계는 다음 뷰로 정의한다. 기능 테이블만 다루는 뷰(`v_leaf_feature`, `v_feature_subtree`)는 [dp1.md](dp1.md)에 있다. 뷰를 정의하는 SQL의 원문은 스킬의 정의 파일(`schema.sql`)에 있다.

| 뷰 | 한 행의 의미 | 열 |
|---|---|---|
| `v_feature_tc` | (말단 기능, 그 기능을 검증하는 TC) 쌍 하나. 중복이 없다. | `feature_id`, `tc_id` |
| `v_scenario_tc_count` | 인스턴스 시나리오 하나 | `scenario_id`, `feature_id`, `tc_count` |
| `v_feature_tc_count` | 말단 기능 하나 | `feature_id`, `scenario_count`, `uncovered_scenario_count`, `tc_count` |
| `v_subtree_tc_count` | 기능 하나. 묶음 기능과 말단 기능을 모두 포함한다. | `feature_id`, `leaf_count`, `uncovered_leaf_count`, `tc_count` |
| `v_unlinked_tc` | 어느 인스턴스 시나리오에도 연결되지 않은 TC 하나 | `tc` 테이블과 같다. |

- `tc_count`는 그 행의 대상에 연결된 TC의 수이며, 같은 TC는 한 번만 센다.
- `scenario_count`는 그 기능에 속한 인스턴스 시나리오의 수다. `uncovered_scenario_count`는 그중에서 TC가 하나도 연결되지 않은 시나리오의 수다.
- `leaf_count`는 그 기능 아래에 있는 말단 기능의 수다. 말단 기능 자신의 행에서는 1이다. `uncovered_leaf_count`는 그중에서 TC가 하나도 연결되지 않은 기능의 수다.

검증 공백은 다음과 같이 구한다.

| 구하는 것 | 방법 |
|---|---|
| 인스턴스 시나리오 단위의 공백 | `v_scenario_tc_count`에서 `tc_count = 0`인 행 |
| 검증되지 않은 기능 | `v_feature_tc_count`에서 `tc_count = 0`인 행 |
| 묶음 기능 아래의 검증되지 않은 기능의 수 | `v_subtree_tc_count`에서 그 묶음의 `uncovered_leaf_count` |

묶음 기능 `NS` 아래에 `NS-CREATE`와 `NS-DELETE`가 있고 관계가 다음과 같은 경우를 예로 든다.

| 인스턴스 시나리오 | 연결된 TC |
|---|---|
| `NS-CREATE-S1` | TC 1, TC 2 |
| `NS-CREATE-S2` | TC 2 |
| `NS-DELETE-S1` | TC 2, TC 3 |

`v_scenario_tc_count`의 `tc_count`는 차례로 2, 1, 2다. `v_feature_tc_count`에서 `NS-CREATE`는 2(TC 1, TC 2), `NS-DELETE`는 2(TC 2, TC 3)다. `v_subtree_tc_count`에서 `NS`는 3(TC 1, TC 2, TC 3)이며, 하위 기능의 값을 더한 4가 아니다.

## 4. 질의 예시

아래 결과는 `examples/`의 **예시 데이터**로 만든 데이터베이스에서 실제로 실행한 결과다. [dp1.md](dp1.md)의 테이블 정의와 뷰를 그대로 사용하였다. 같은 질의와 결과를 `tests/test_ftm_query.py`의 `QueryExamples`와 `AggregateViews`에서 확인한다.

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

### 검증되지 않은 기능은 무엇인가

```sql
SELECT feature_id FROM v_feature_tc_count WHERE tc_count = 0;
```

| feature_id |
|---|
| PS-TRANSITION |

### TC가 연결되지 않은 인스턴스 시나리오는 무엇인가

```sql
SELECT scenario_id, feature_id FROM v_scenario_tc_count WHERE tc_count = 0 ORDER BY scenario_id;
```

| scenario_id | feature_id |
|---|---|
| PS-TRANSITION-S1 | PS-TRANSITION |
| SANITIZE-S2 | SANITIZE |

`SANITIZE`는 TC가 3개 연결된 기능이지만, 두 번째 인스턴스 시나리오(진행 중에 전원이 꺼지는 경우)에는 TC가 없다. 기능 단위의 집계에서는 이 공백이 드러나지 않는다.

### Namespace Create를 검증하는 TC는 무엇인가

```sql
SELECT t.id, t.suite, t.name
FROM v_feature_tc ft JOIN tc t ON t.id = ft.tc_id
WHERE ft.feature_id = 'NS-CREATE'
ORDER BY t.id;
```

| id | suite | name |
|---|---|---|
| 1 | tc/nvme_admin | ns_create_basic |
| 2 | tc/nvme_admin | ns_create_max_count |
| 3 | tc/nvme_admin | ns_create_no_capacity |
| 4 | tc/nvme_admin | ns_create_delete_loop |

### 묶음 기능 NS를 검증하는 TC는 몇 개인가

```sql
SELECT feature_id, leaf_count, uncovered_leaf_count, tc_count FROM v_subtree_tc_count WHERE feature_id = 'NS';
```

| feature_id | leaf_count | uncovered_leaf_count | tc_count |
|---|---|---|---|
| NS | 2 | 0 | 5 |

`NS-CREATE`의 TC는 4개, `NS-DELETE`의 TC는 2개이지만, TC 4(`ns_create_delete_loop`)가 두 기능을 함께 검증하므로 `NS`의 TC는 5개다.

### 여러 기능을 함께 검증하는 TC는 무엇인가

```sql
SELECT t.id, t.suite, t.name, COUNT(*) AS feature_count
FROM v_feature_tc ft JOIN tc t ON t.id = ft.tc_id
GROUP BY t.id
HAVING COUNT(*) > 1
ORDER BY t.id;
```

| id | suite | name | feature_count |
|---|---|---|---|
| 4 | tc/nvme_admin | ns_create_delete_loop | 2 |
| 17 | tc/power | flush_then_spo | 2 |

### 어느 인스턴스 시나리오에도 연결되지 않은 TC는 무엇인가

```sql
SELECT id, suite, name FROM v_unlinked_tc ORDER BY id;
```

| id | suite | name |
|---|---|---|
| 18 | tc/fio_io | seq_read_baseline |
| 19 | tc/nvme_admin | smart_log_read |
| 20 | tc/nvme_admin | identify_controller |
