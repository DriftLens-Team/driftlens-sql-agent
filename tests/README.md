# 테스트 실행

패키지를 설치한 같은 Python 환경에서 다음 명령을 실행합니다.

```powershell
python -m unittest discover -s tests/unit -p "test_*.py" -v
```

현재 검증 범위는 설치된 패키지의 도움말·버전·미구현 실행 거부·프로토콜 인자 검증입니다. 임시 작업 디렉터리에서 PYTHONPATH 없이 실행하여 저장소 루트의 파일에 우연히 의존하지 않도록 합니다.

실제 DB/모델/JSONL 테스트는 [검증 계획](../docs/contracts/v1/validation.md)에 따라 후속 구현과 함께 추가합니다. 아직 필요하지 않은 integration/fixtures 폴더는 만들지 않습니다. 모듈별 테스트 폴더가 늘어나면 명시적인 탐색 명령도 함께 갱신합니다.
