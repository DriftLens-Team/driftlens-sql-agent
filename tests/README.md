# 테스트 실행

패키지를 설치한 같은 Python 환경에서 실행합니다.

```powershell
python -m unittest discover -s tests/unit -p "test_*.py" -v
```

현재 20개 테스트는 CLI, 설정·profile·요청, 임시 SQLite의 조회·쓰기 차단·예산·잠금, 경계값/기간 변화, 요청 격리, 복구, 인증 실패와 일시 오류, 호출/요청 시간 제한, 진단 범위를 확인합니다. 응답하지 않는 모델은 별도 프로세스에서 강제 종료합니다. 외부 키나 benchmark 체크아웃은 필요하지 않습니다.

CLI 테스트는 임시 작업 디렉터리에서 PYTHONPATH 없이 설치된 패키지를 실행합니다. runtime 테스트는 fake/scripted 모델을 쓰므로 실제 LLM 정확도 결과가 아닙니다. JSONL·HTTP·CI는 4단계, live 평가는 5단계입니다. [검증 계획](../docs/contracts/v1/validation.md)에 따라 후속 테스트를 추가합니다.
