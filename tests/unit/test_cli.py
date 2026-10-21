"""Validate installed entry-point behavior without a benchmark checkout or API key."""

from importlib.metadata import version
import os
import subprocess
import sys
import tempfile
import unittest


class InstalledCliTests(unittest.TestCase):
    def run_cli(self, *args):
        # Run outside the checkout; PYTHONPATH must not hide packaging mistakes.
        """설치 누락을 숨기지 않도록 저장소 밖에서 CLI를 실행한다."""
        with tempfile.TemporaryDirectory() as directory:
            env = {key: value for key, value in os.environ.items() if key.upper() != "PYTHONPATH"}
            return subprocess.run(
                [sys.executable, "-m", "driftlens_sql_agent", *args],
                cwd=directory, env=env, text=True, capture_output=True, timeout=10,
            )

    def test_help_is_available_without_runtime_configuration(self):
        """설정 없이 도움말을 조회할 수 있는지 확인한다."""
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UTF-8 JSONL", result.stdout)
        self.assertIn("--profile", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_version_matches_installed_metadata(self):
        """표시 버전이 설치된 패키지 메타데이터와 일치하는지 확인한다."""
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"driftlens-sql-agent {version('driftlens-sql-agent')}")

    def test_runtime_request_cannot_report_fake_success(self):
        """설정 누락을 성공이나 fake 응답으로 숨기지 않는지 확인한다."""
        result = self.run_cli("--config", "missing.json", "--profile", "missing-profile.json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("invalid_config", result.stderr)

    def test_unsupported_protocol_is_rejected(self):
        """지원하지 않는 프로토콜 버전의 시작을 거부하는지 확인한다."""
        result = self.run_cli("--config", "x", "--profile", "y", "--protocol-version", "v2")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
