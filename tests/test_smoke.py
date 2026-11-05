"""End-to-end checks against the real macOS caffeinate."""

import os
import shutil
import subprocess
import sys
import time
import unittest

from helpers import COMMAND, run_in_terminal

REAL = shutil.which("caffeinate", path="/usr/bin")


@unittest.skipUnless(sys.platform == "darwin" and REAL, "needs macOS caffeinate")
class RealCaffeinateTests(unittest.TestCase):
    def environment(self):
        env = os.environ.copy()
        env["PATH"] = "/usr/bin:/bin"
        return env

    def test_timeout_without_terminal(self):
        started = time.monotonic()
        result = subprocess.run(
            [str(COMMAND), "-t", "1"], env=self.environment(), capture_output=True, timeout=10
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertGreaterEqual(time.monotonic() - started, 0.9)

    def test_invalid_option_passes_caffeinate_error_through(self):
        result = subprocess.run(
            [str(COMMAND), "-z"], env=self.environment(), capture_output=True, text=True, timeout=10
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage", result.stderr.lower())

    def test_animates_on_a_terminal(self):
        # run_in_terminal puts a stand-in first on PATH; an empty directory falls
        # through to the real caffeinate, which runs "-t 1" here.
        status, output = run_in_terminal(0, ("-t", "1"), PATH="/var/empty:/usr/bin:/bin")

        self.assertEqual(status, 0)
        self.assertIn(b"\x1b[?25l", output)
        self.assertTrue(output.endswith(b"\x1b[J\x1b[?25h"))


if __name__ == "__main__":
    unittest.main()
