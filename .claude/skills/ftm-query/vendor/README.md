# vendor

이 폴더는 외부 패키지의 사본을 담는다.

| 폴더 | 패키지 | 버전 | 라이선스 |
|---|---|---|---|
| `yaml/` | PyYAML | 6.0.3 | MIT (`yaml/LICENSE`) |

`yaml/`은 PyYAML의 순수 Python 모듈만 포함하며, C 확장(`_yaml`)은 포함하지 않는다. 변환 명령(`scripts/build.py`)은 설치된 PyYAML이 있으면 그것을 사용하고, 없으면 이 사본을 사용한다. 사본의 파일은 고치지 않는다.
