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


def run_in_terminal(columns, rows, child_seconds, resize_to=None):
    """Run macchiato on a pseudo-terminal and return everything it drew."""
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory)
        child = fixture / "caffeinate"
        child.write_text(f"#!/bin/bash\nsleep {child_seconds}\n")
        child.chmod(0o755)
        environment = os.environ.copy()
        environment["PATH"] = f"{fixture}:{environment['PATH']}"
        master, slave = os.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
        try:
            process = subprocess.Popen(
                [str(COMMAND)],
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=slave,
            )
            output = bytearray()
            started = time.monotonic()
            while True:
                if resize_to and time.monotonic() - started > child_seconds / 2:
                    new_columns, new_rows = resize_to
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", new_rows, new_columns, 0, 0))
                    process.send_signal(signal.SIGWINCH)
                    resize_to = None
                ready, _, _ = select.select([master], [], [], 0.1)
                if ready:
                    output.extend(os.read(master, 65536))
                elif process.poll() is not None:
                    break
                if time.monotonic() - started > child_seconds + 3:
                    raise AssertionError("terminal output did not finish")
            assert process.wait(timeout=2) == 0
        finally:
            os.close(slave)
            os.close(master)
        return bytes(output)


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

            text = output.decode()
            self.assertTrue(set("▘▝▖▗▀▄▌▐▚▞▙▛▜▟") & set(text), "cup is not drawn with block pixels")
            self.assertIn(b"\x1b[38;2;203;154;109m", output)
            self.assertIn(b"\x1b[48;2;70;50;37m", output)
            self.assertIn(b"Brewing some wakefulness", output)
            self.assertIn(b"Your Mac is staying awake", output)
            self.assertIn(b"Press Ctrl+C to finish your coffee", output)
            self.assertIn(b"\x1b[38;2;", output)
            self.assertIn(b"\x1b[48;2;", output)
            self.assertIn(b"\x1b[?25l", output)
            self.assertIn(b"\x1b[?25h", output)
            self.assertTrue(output.endswith(b"\x1b[J\x1b[?25h"), "drawing is not cleared on exit")

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
                # Keep draining like a real terminal so a pending frame can finish.
                deadline = time.monotonic() + 2
                while process.poll() is None and time.monotonic() < deadline:
                    ready, _, _ = select.select([master], [], [], 0.1)
                    if ready:
                        output.extend(os.read(master, 4096))
                self.assertEqual(process.wait(timeout=1), 130)
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

            text = output.decode()
            self.assertTrue(set("▘▝▖▗▀▄▌▐▚▞▙▛▜▟") & set(text), "compact cup is missing")
            self.assertIn("✓ \x1b[38;2;178;183;188mMac staying awake", text)
            self.assertNotIn("Press Ctrl+C to finish your coffee", text)
            self.assertIn(b"\x1b[?25h", output)

    def test_short_terminal_shows_status_without_cup(self):
        output = run_in_terminal(columns=80, rows=10, child_seconds=0.4)

        text = output.decode()
        self.assertFalse(set("▘▝▖▗▀▄▌▐▚▞▙▛▜▟") & set(text), "cup does not fit a short terminal")
        self.assertIn("Your Mac is staying awake", text)
        self.assertIn("Press Ctrl+C to finish your coffee", text)
        self.assertTrue(output.endswith(b"\x1b[J\x1b[?25h"))

    def test_redraws_for_new_terminal_size(self):
        output = run_in_terminal(columns=80, rows=24, child_seconds=1.2, resize_to=(32, 24))

        before, _, after = output.decode().partition("\x1b[J")
        self.assertIn("Your Mac is staying awake", before)
        self.assertIn("Mac staying awake", after)
        self.assertNotIn("Your Mac is staying awake", after)


if __name__ == "__main__":
    unittest.main()
