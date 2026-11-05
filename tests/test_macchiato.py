import fcntl
import json
import os
from pathlib import Path
import select
import signal
import struct
import subprocess
import tempfile
import termios
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMMAND = ROOT / "bin" / "macchiato"


class MacchiatoTests(unittest.TestCase):
    def test_forwards_arguments_output_and_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            child = fixture / "caffeinate"
            child.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "with open(os.environ['MACCHIATO_ARGS_FILE'], 'w') as output:\n"
                "    json.dump(sys.argv[1:], output)\n"
                "print('child stdout')\n"
                "print('child stderr', file=sys.stderr)\n"
                "sys.exit(23)\n"
            )
            child.chmod(0o755)
            args_file = fixture / "args.json"
            environment = os.environ.copy()
            environment["PATH"] = f"{fixture}:{environment['PATH']}"
            environment["MACCHIATO_ARGS_FILE"] = str(args_file)

            self.assertTrue(COMMAND.exists(), "macchiato command is missing")
            result = subprocess.run(
                [str(COMMAND), "-t", "5", "spaced argument", ""],
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
            )

            self.assertEqual(json.loads(args_file.read_text()), ["-t", "5", "spaced argument", ""])
            self.assertEqual(result.returncode, 23)
            self.assertEqual(result.stdout, "child stdout\n")
            self.assertEqual(result.stderr, "child stderr\n")

    def test_animates_and_restores_terminal_while_child_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            child = fixture / "caffeinate"
            child.write_text("#!/bin/bash\nsleep 0.9\n")
            child.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{fixture}:{environment['PATH']}"
            master, slave = os.openpty()
            try:
                process = subprocess.Popen(
                    [str(COMMAND)],
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=slave,
                )
                os.close(slave)
                slave = -1
                output = bytearray()
                while True:
                    ready, _, _ = select.select([master], [], [], 2)
                    if not ready:
                        self.fail("terminal output did not finish")
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output.extend(chunk)
                self.assertEqual(process.wait(timeout=2), 0)
            finally:
                if slave >= 0:
                    os.close(slave)
                os.close(master)

            self.assertIn("╭────────────────────╮".encode(), output)
            self.assertIn("╭    ╮    ╭".encode(), output)
            self.assertIn("╮    ╭    ╮".encode(), output)
            self.assertIn("│    │    │".encode(), output)
            self.assertIn(b"Brewing some wakefulness", output)
            self.assertIn(b"Your Mac is staying awake", output)
            self.assertIn(b"Press Ctrl+C to finish your coffee", output)
            self.assertIn(b"\x1b[38;2;", output)
            self.assertIn(b"\x1b[48;2;", output)
            self.assertIn(b"\x1b[?25l", output)
            self.assertIn(b"\x1b[?25h", output)
            self.assertIn(b"\x1b[2K", output)

    def test_interrupt_stops_child_and_restores_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            child = fixture / "caffeinate"
            pid_file = fixture / "pid"
            child.write_text("#!/bin/bash\necho \"$$\" > \"$MACCHIATO_PID_FILE\"\nexec sleep 30\n")
            child.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{fixture}:{environment['PATH']}"
            environment["MACCHIATO_PID_FILE"] = str(pid_file)
            master, slave = os.openpty()
            try:
                process = subprocess.Popen(
                    [str(COMMAND)],
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=slave,
                )
                deadline = time.monotonic() + 2
                while not pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(pid_file.exists())
                output = bytearray()
                while b"\x1b[?25l" not in output and time.monotonic() < deadline:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if ready:
                        output.extend(os.read(master, 4096))
                self.assertIn(b"\x1b[?25l", output)
                os.kill(process.pid, signal.SIGINT)
                self.assertEqual(process.wait(timeout=2), 130)
                deadline = time.monotonic() + 2
                while b"\x1b[?25h" not in output and time.monotonic() < deadline:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if ready:
                        output.extend(os.read(master, 4096))
                self.assertIn(b"\x1b[?25h", output)
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(pid_file.read_text()), 0)
            finally:
                if slave >= 0:
                    os.close(slave)
                os.close(master)

    def test_narrow_terminal_uses_compact_cup(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            child = fixture / "caffeinate"
            child.write_text("#!/bin/bash\nsleep 0.4\n")
            child.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{fixture}:{environment['PATH']}"
            master, slave = os.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 32, 0, 0))
            try:
                process = subprocess.Popen(
                    [str(COMMAND)],
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=slave,
                )
                os.close(slave)
                slave = -1
                output = bytearray()
                while True:
                    ready, _, _ = select.select([master], [], [], 2)
                    self.assertTrue(ready)
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    output.extend(chunk)
                self.assertEqual(process.wait(timeout=2), 0)
            finally:
                if slave >= 0:
                    os.close(slave)
                os.close(master)

            self.assertIn("╭────────────╮".encode(), output)
            self.assertIn(b"Mac staying awake", output)
            self.assertIn(b"\x1b[?25h", output)


if __name__ == "__main__":
    unittest.main()
