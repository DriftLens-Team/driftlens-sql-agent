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
        with tempfile.TemporaryDirectory() as directory:
            env = {key: value for key, value in os.environ.items() if key.upper() != "PYTHONPATH"}
            return subprocess.run(
                [sys.executable, "-m", "driftlens_sql_agent", *args],
                cwd=directory, env=env, text=True, capture_output=True, timeout=10,
            )

    def test_help_is_available_without_runtime_configuration(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("UTF-8 JSONL", result.stdout)
        self.assertIn("--profile", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_version_matches_installed_metadata(self):
        result = self.run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), f"driftlens-sql-agent {version('driftlens-sql-agent')}")

    def test_runtime_request_cannot_report_fake_success(self):
        result = self.run_cli("--config", "missing.json", "--profile", "missing-profile.json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("invalid_config", result.stderr)

    def test_unsupported_protocol_is_rejected(self):
        result = self.run_cli("--config", "x", "--profile", "y", "--protocol-version", "v2")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
