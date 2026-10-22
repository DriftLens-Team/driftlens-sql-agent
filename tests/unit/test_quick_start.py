"""로컬 비밀값을 읽지 않고 빠른 시작의 모델 선택과 실제 CLI 경계를 검증한다."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


class QuickStartTests(unittest.TestCase):
    def setUp(self):
        """테스트 훅: 저장소의 .env와 기존 DB를 건드리지 않는 복사본을 준비한다."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for relative in ["scripts/start.py", "scripts/prepare_debug.py", "configs/runtime.example.json",
                         "profiles/v1/profile.example.json"]:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.env = {key: value for key, value in os.environ.items()
                    if key.upper() not in {"UPSTAGE_MODEL", "UPSTAGE_API_KEY"}}

    def run_start(self, content=None, extra=None, request=""):
        """여러 설정 조합에서 동일한 프로세스 실행·입출력 경계를 검증한다."""
        path = self.root / ".env"
        if content is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(content, encoding="utf-8")
        return subprocess.run([sys.executable, str(self.root / "scripts/start.py")],
                              input=request, text=True, encoding="utf-8", capture_output=True,
                              env={**self.env, "PYTHONUTF8": "1", **(extra or {})}, timeout=20)

    def test_absent_settings_run_real_cli_with_fake(self):
        """설정이 없으면 실제 CLI가 fake로 질문을 처리하고 stdout에는 응답만 쓴다."""
        request = json.dumps({"request_id": "quick-1", "request": "이번 주 대형 주문은 몇 건인가요?",
                              "period": "2025-W03", "timestamp": "2025-01-19T23:59:59Z"}) + "\n"
        result = self.run_start(request=request)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["observation"]["reported_values"][0]["value"], 2)
        self.assertIn("Model: fake", result.stderr)

    def test_empty_file_and_comments_mean_absent(self):
        """빈 파일·주석만 있는 파일은 자격 증명 미지정으로 처리한다."""
        for content in ["", "# optional credentials\n\n"]:
            with self.subTest(content=content):
                result = self.run_start(content)
                self.assertEqual(result.returncode, 0)
                self.assertIn("Model: fake", result.stderr)

    def test_complete_settings_select_upstage_without_call_on_eof(self):
        """두 설정이 있으면 upstage로 시작하며 EOF만 주면 외부 호출은 없다."""
        for content, extra in [
            ('UPSTAGE_MODEL="test-model"\nUPSTAGE_API_KEY=\'SECRET_SENTINEL\'\n', None),
            (None, {"UPSTAGE_MODEL": "test-model", "UPSTAGE_API_KEY": "SECRET_SENTINEL"}),
            ('UPSTAGE_MODEL=test-model', {"UPSTAGE_API_KEY": "SECRET_SENTINEL"}),
        ]:
            with self.subTest(source=bool(content)):
                result = self.run_start(content, extra)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Model: upstage", result.stderr)
                self.assertNotIn("SECRET_SENTINEL", result.stdout + result.stderr)

    def test_partial_and_blank_settings_fail(self):
        """부분·공백·명시적인 빈 값은 fake로 숨기지 않고 실패한다."""
        for content in ["UPSTAGE_MODEL=x", "UPSTAGE_API_KEY=SECRET_SENTINEL",
                        "UPSTAGE_MODEL=\nUPSTAGE_API_KEY=", 'UPSTAGE_MODEL=" "\nUPSTAGE_API_KEY=x']:
            with self.subTest(content=content):
                result = self.run_start(content)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Model:", result.stderr)
                self.assertNotIn("SECRET_SENTINEL", result.stdout + result.stderr)

    def test_environment_has_precedence_including_blank(self):
        """환경의 명시적인 빈 값도 .env의 정상 값으로 덮어쓰지 않는다."""
        result = self.run_start("UPSTAGE_MODEL=file\nUPSTAGE_API_KEY=file-secret",
                                {"UPSTAGE_MODEL": "", "UPSTAGE_API_KEY": "env-secret"})
        self.assertEqual(result.returncode, 2)
        self.assertIn("UPSTAGE_MODEL", result.stderr)

    def test_invalid_env_fails_without_echo(self):
        """잘못된 문법·중복·열린 따옴표를 값 노출 없이 거부한다."""
        for content in ["SECRET_SENTINEL", "UPSTAGE_MODEL=x\nUPSTAGE_MODEL=y",
                        'UPSTAGE_API_KEY="SECRET_SENTINEL']:
            with self.subTest(content=content):
                result = self.run_start(content)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("SECRET_SENTINEL", result.stdout + result.stderr)

    def test_existing_config_and_database_are_preserved(self):
        """모델 자동 선택은 기존 설정·DB를 변경하지 않고 실행용 파일을 정리한다."""
        self.assertEqual(self.run_start().returncode, 0)
        folder = self.root / "runs/local-debug"
        paths = [folder / "runtime.json", folder / "orders.sqlite"]
        before = [path.read_bytes() for path in paths]
        result = self.run_start("UPSTAGE_MODEL=x\nUPSTAGE_API_KEY=SECRET_SENTINEL")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(before, [path.read_bytes() for path in paths])
        self.assertEqual(list(folder.glob("session-*.json")), [])

    def test_cli_failure_is_not_retried_as_fake(self):
        """CLI 실패는 그대로 반환하며 다른 모델로 재호출하지 않는다."""
        spec = importlib.util.spec_from_file_location("quick_start_under_test", self.root / "scripts/start.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        (self.root / ".env").write_text("UPSTAGE_MODEL=file\nUPSTAGE_API_KEY=file-key", encoding="utf-8")
        calls = []

        def failing_cli(args):
            """모의 CLI 콜백: 실제 전달된 설정·환경을 기록하고 실패 종료를 반환한다."""
            config = json.loads(Path(args[1]).read_text(encoding="utf-8"))
            calls.append((config["model"]["provider"], os.environ["UPSTAGE_MODEL"]))
            return 1

        with patch.dict(os.environ, {**self.env, "UPSTAGE_MODEL": "env-model"}, clear=True), \
                patch.object(module, "cli_main", side_effect=failing_cli), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(module.main(), 1)
        self.assertEqual(calls, [("upstage", "env-model")])
        self.assertEqual(list((self.root / "runs/local-debug").glob("session-*.json")), [])
