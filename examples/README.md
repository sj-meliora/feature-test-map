# 예시 데이터

이 폴더의 파일은 모두 **예시 데이터**다. 실제 IMS structure, TC 저장소, 관계 식별 결과에서 얻은 내용이 아니며, 실제 데이터와 섞어 쓰지 않는다.

JSONL 형식은 주석을 남길 수 없으므로, 예시라는 표시를 이 문서로 대신한다.

| 파일 | 테이블 | 형식 | 레코드 수 |
|---|---|---|---|
| `features.yaml` | 기능 (DP-1) | YAML | 8 (묶음 1, 검증 대상 7) |
| `scenarios.yaml` | 인스턴스 시나리오 (DP-7) | YAML | 8 |
| `tcs.jsonl` | TC (DP-2) | JSONL | 10 |
| `scenario_tc.jsonl` | 시나리오-TC 관계 (DP-3) | JSONL | 10 |

예시 데이터는 다음 상황을 포함하도록 구성하였다.

- `NS`는 하위 항목을 가지는 묶음이며, `NS-CREATE`와 `NS-DELETE`가 검증 대상이다. 나머지 기능은 최상위 말단 항목이다.
- `NS-CREATE`에는 인스턴스 시나리오가 두 개 있다. `NS-CREATE.S2`에는 TC가 연결되어 있지 않다.
- `NS-CREATE.S1`에 연결된 TC 2(`ns_create_max_count`)는 `NS-CREATE.S1`의 조합에 해당하지 않지만, 해당하는 시나리오가 아직 없어서 옮겨지지 않은 TC다.
- `SANITIZE`는 인스턴스 시나리오에 TC가 하나도 연결되지 않은 기능이다.
- TC 7(`rand_rw_mix`)은 어느 인스턴스 시나리오에도 연결되지 않은 TC다.
- TC 10(`spor_after_flush`)은 두 기능(`FLUSH`, `SPOR`)을 검증하는 TC다.

이 데이터로 SQLite 데이터베이스를 만들고 조회한 결과는 `docs/sqlite-query-design.md`의 '질의 예시'에 있다.
