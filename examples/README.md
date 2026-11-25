# 예시 데이터

이 폴더의 파일은 모두 **예시 데이터**다. 실제 IMS structure에서 추출한 내용이 아니며, 실제 데이터와 섞어 쓰지 않는다.

| 파일 | 테이블 | 형식 | 레코드 수 |
|---|---|---|---|
| `features.yaml` | 기능 (DP-1) | YAML | 8 (묶음 1, 검증 대상 7) |
| `scenarios.yaml` | 인스턴스 시나리오 (DP-7) | YAML | 9 |
| `tcs.jsonl` | TC (DP-2) | JSONL | 20 |
| `scenario_tc.jsonl` | 시나리오-TC 관계 (DP-3) | JSONL | 19 |

TC의 suite, 이름, 소스 코드 이름, 운영 조직, 실행 환경은 지어낸 값이며, 가리키는 소스 코드는 없다. 시나리오-TC 관계도 지어낸 값이며, TC의 내용을 분석하여 식별한 결과가 아니다.

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
| 운영 조직과 실행 환경이 다른 TC | `owner`가 `sv`이고 `platform`이 `msvp`인 TC가 12개, `owner`가 `sw-dev`이고 `platform`이 `hapsim`인 TC가 8개(TC 2, 3, 8, 9, 10, 11, 13, 19)다. |
| 모든 TC를 기준으로 하면 검증되지만 한 분류를 기준으로 하면 검증되지 않는 기능 | `SANITIZE`의 TC는 모두 `sw-dev`의 TC이므로 `sv`를 기준으로 하면 검증되지 않는다. `NS-DELETE`와 `SPOR`의 TC는 모두 `sv`의 TC이므로 `sw-dev`를 기준으로 하면 검증되지 않는다. |
| 한 분류를 기준으로 할 때에만 TC가 없는 인스턴스 시나리오 | `NS-CREATE-S2`의 TC는 `sw-dev`의 TC 하나뿐이므로 `sv`를 기준으로 하면 TC가 없다. |
| 묶음 기능의 결과가 하위 기능의 합으로 계산되는 경우 | `NS`의 TC는 5개다. `NS-CREATE`의 4개와 `NS-DELETE`의 2개 중 TC 4가 겹친다. |

이 데이터로 SQLite 데이터베이스를 만들고 조회한 결과는 `design/dp5.md`의 '질의 예시'에 있다.

## 데모 실행

저장소 최상위에서 실행한다. Python 3이 필요하다. PyYAML이 설치되어 있지 않으면 스킬에 포함된 사본을 사용한다. 아래의 명령은 bash 계열의 셸을 기준으로 적었다. Windows에서는 `python3` 대신 `python`을 쓰며, 1번의 환경 변수는 아래 'Windows에서'의 방법으로 지정한다.

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

변환 명령과 보고서 명령은 환경 변수 대신 `--data-dir` 인자로 데이터 폴더를 받을 수도 있다.

```bash
python3 .claude/skills/ftm-query/scripts/build.py --data-dir examples
```

에이전트 없이 조회 스크립트를 직접 실행할 수도 있다.

```bash
python3 .claude/skills/ftm-query/scripts/query.py schema
```

```bash
python3 .claude/skills/ftm-query/scripts/query.py sql "SELECT * FROM v_feature_tc_count"
```

원본 파일을 고친 뒤에는 2번의 변환 명령과 4번의 보고서 명령을 다시 실행한다. 변환 명령을 다시 실행하지 않으면 조회 스크립트와 보고서 명령이 오류로 종료하고 실행할 명령을 안내한다.

### Windows에서

환경 변수는 셸에 따라 다음과 같이 지정한다. 에이전트는 이 환경 변수가 지정된 셸에서 실행해야 조회 스크립트가 데이터 폴더를 찾는다.

| 셸 | 지정하는 방법 |
|---|---|
| PowerShell | `$env:FTM_DATA_DIR = "$PWD\examples"` |
| cmd | `set "FTM_DATA_DIR=%CD%\examples"` |
| Git Bash | `export FTM_DATA_DIR="$PWD/examples"` |

조회 스크립트의 오류 메시지에 있는 실행 줄은 세 셸에서 모두 그대로 실행되도록 적혀 있다.
