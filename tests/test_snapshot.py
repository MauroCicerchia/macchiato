"""Golden snapshots of the drawing, so geometry and color changes are visible in review.

Frames are deterministic: each one ends with the same synchronized-output
marker, so the N-th frame is the same regardless of timing. To accept an
intended change, run `make snapshots` and review the diff.
"""

import os
import signal
import unittest

from helpers import ROOT, TerminalSession, screen_after

SNAPSHOTS = ROOT / "tests" / "snapshots"
FRAME = 20  # after the steam's intro


class SnapshotTests(unittest.TestCase):
    def check(self, name, columns, rows):
        with TerminalSession("exec sleep 30\n", columns=columns, rows=rows) as session:
            session.wait_for(lambda: session.frames() > FRAME, timeout=10)
            session.process.send_signal(signal.SIGINT)
            session.finish()
            actual = screen_after(session.output, FRAME, columns, rows).dump()

        path = SNAPSHOTS / f"{name}.txt"
        if os.environ.get("UPDATE_SNAPSHOTS"):
            path.write_text(actual)
        self.assertTrue(path.exists(), f"missing {path}; run `make snapshots`")
        self.assertEqual(actual, path.read_text(), f"{name} changed; run `make snapshots` if intended")

    def test_standard_terminal(self):
        self.check("80x24", 80, 24)

    def test_narrow_terminal(self):
        self.check("32x24", 32, 24)


if __name__ == "__main__":
    unittest.main()
