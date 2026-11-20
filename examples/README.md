# 예시 데이터

이 폴더의 파일은 모두 **예시 데이터**다. 실제 IMS structure에서 추출한 내용이 아니며, 실제 데이터와 섞어 쓰지 않는다.

| 파일 | 테이블 | 형식 | 레코드 수 |
|---|---|---|---|
| `features.yaml` | 기능 (DP-1) | YAML | 8 (묶음 1, 검증 대상 7) |

예시 데이터는 다음 상황을 포함하도록 구성하였다.

- 대부분의 기능은 하위 항목이 없는 최상위 항목이다. IMS structure가 최상위 목록 위주로 구성된다는 전제를 따른다.
- `NS`는 하위 항목을 가지는 묶음이며, 검증 대상이 아니다. 그 아래의 `NS-CREATE`와 `NS-DELETE`가 검증 대상이다.

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

   - 검증 대상인 기능은 몇 개인가?
   - namespace 관련 기능 중 검증 대상은 무엇인가?
   - Sanitize는 어떤 기능인가?

에이전트 없이 조회 스크립트를 직접 실행할 수도 있다.

```bash
python3 .claude/skills/ftm-query/scripts/query.py schema
```

```bash
python3 .claude/skills/ftm-query/scripts/query.py sql "SELECT COUNT(*) AS leaf_count FROM v_leaf_feature"
```

`features.yaml`을 고친 뒤에는 2번의 변환 명령을 다시 실행한다. 다시 실행하지 않으면 조회 스크립트가 오류로 종료하고 실행할 명령을 안내한다.
