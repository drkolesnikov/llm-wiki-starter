import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ValidateRepoHealthTests(unittest.TestCase):
    def test_health_report_is_non_blocking_and_reports_sections(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "validate_repo.py"), "--health-report"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Repository validation passed.", result.stdout)
        self.assertIn("Wiki health report", result.stdout)
        self.assertIn("Unresolved statuses", result.stdout)
        self.assertIn("Orphan candidates", result.stdout)


if __name__ == "__main__":
    unittest.main()
