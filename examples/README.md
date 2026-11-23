# 예시 데이터

이 폴더의 파일은 모두 **예시 데이터**다. 실제 IMS structure에서 추출한 내용이 아니며, 실제 데이터와 섞어 쓰지 않는다.

| 파일 | 테이블 | 형식 | 레코드 수 |
|---|---|---|---|
| `features.yaml` | 기능 (DP-1) | YAML | 8 (묶음 1, 검증 대상 7) |
| `scenarios.yaml` | 인스턴스 시나리오 (DP-7) | YAML | 9 |
| `tcs.jsonl` | TC (DP-2) | JSONL | 20 |
| `scenario_tc.jsonl` | 시나리오-TC 관계 (DP-3) | JSONL | 19 |

TC의 suite, 이름, 소스 코드 이름은 지어낸 값이며, 가리키는 소스 코드는 없다. 시나리오-TC 관계도 지어낸 값이며, TC의 내용을 분석하여 식별한 결과가 아니다.

예시 데이터는 다음 상황을 포함하도록 구성하였다.

| 상황 | 예시 데이터에서 해당하는 부분 |
|---|---|
| 대부분의 기능은 하위 항목이 없는 최상위 항목이다. | `FORMAT`, `SANITIZE`, `FLUSH`, `PS-TRANSITION`, `SPOR` |
| 하위 항목을 가지는 묶음은 검증 대상이 아니다. | `NS`는 묶음이고, 그 아래의 `NS-CREATE`와 `NS-DELETE`가 검증 대상이다. |
| TC가 여러 개 연결된 기능 | `NS-CREATE`(4개), `SPOR`(4개) 등 |
| TC가 하나도 연결되지 않은 기능 | `PS-TRANSITION` |
| 인스턴스 시나리오가 두 개이고 그중 하나에만 TC가 연결된 기능 | `SANITIZE`. `SANITIZE-S1`에는 TC가 3개 있고, `SANITIZE-S2`에는 없다. |
| 인스턴스 시나리오가 두 개이고 둘 다 TC가 연결된 기능 | `NS-CREATE` |
| 두 기능을 함께 검증하는 TC | TC 4(`ns_create_delete_loop`)는 `NS-CREATE`와 `NS-DELETE`를, TC 17(`flush_then_spo`)은 `FLUSH`와 `SPOR`를 검증한다. |
| 어느 인스턴스 시나리오에도 연결되지 않은 TC | TC 18, 19, 20 |
| 묶음 기능의 결과가 하위 기능의 합으로 계산되는 경우 | `NS`의 TC는 5개다. `NS-CREATE`의 4개와 `NS-DELETE`의 2개 중 TC 4가 겹친다. |

이 데이터로 SQLite 데이터베이스를 만들고 조회한 결과는 `design/dp5.md`의 '질의 예시'에 있다.

## 데모 실행

저장소 최상위에서 실행한다. Python 3이 필요하다. PyYAML이 설치되어 있지 않으면 스킬에 포함된 사본을 사용한다.

1. 데이터 폴더의 경로를 환경 변수로 지정한다.

   ```bash
   export FTM_DATA_DIR="$PWD/examples"
   ```

2. 변환 명령을 실행하여 데이터베이스(`examples/build/ftm.db`)를 만든다. 이 파일은 git에 넣지 않는다.

   ```bash
   python3 .claude/skills/ftm-query/scripts/build.py
   ```

3. 같은 셸에서 에이전트를 실행하고 질의한다. 에이전트는 `ftm-query` 스킬로 답한다.

   - 검증되지 않은 기능은 무엇인가?
   - Sanitize는 충분히 검증되고 있는가?
   - namespace 관련 기능을 검증하는 TC는 몇 개인가?
   - Sanitize는 어떤 기능인가?

4. 검증 공백 보고서를 만든다. `examples/build/report.html`이 만들어지며, 브라우저로 연다.

   ```bash
   python3 .claude/skills/ftm-query/report/report.py
   ```

에이전트 없이 조회 스크립트를 직접 실행할 수도 있다.

```bash
python3 .claude/skills/ftm-query/scripts/query.py schema
```

```bash
python3 .claude/skills/ftm-query/scripts/query.py sql "SELECT * FROM v_feature_tc_count"
```

원본 파일을 고친 뒤에는 2번의 변환 명령과 4번의 보고서 명령을 다시 실행한다. 변환 명령을 다시 실행하지 않으면 조회 스크립트와 보고서 명령이 오류로 종료하고 실행할 명령을 안내한다.
