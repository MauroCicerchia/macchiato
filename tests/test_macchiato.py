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
import threading
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


class TerminalSession:
    """macchiato on a pseudo-terminal used as stdin and stderr, like a shell runs it."""

    def __init__(self, child_script, arguments=()):
        self.directory = tempfile.TemporaryDirectory()
        fixture = Path(self.directory.name)
        child = fixture / "caffeinate"
        child.write_text("#!/bin/bash\necho \"$$\" > \"$MACCHIATO_PID_FILE\"\n" + child_script)
        child.chmod(0o755)
        self.pid_file = fixture / "pid"
        environment = os.environ.copy()
        environment["PATH"] = f"{fixture}:{environment['PATH']}"
        environment["MACCHIATO_PID_FILE"] = str(self.pid_file)
        self.master, self.slave = os.openpty()
        fcntl.ioctl(self.slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
        self.output = bytearray()
        self.process = subprocess.Popen(
            [str(COMMAND), *arguments],
            env=environment,
            stdin=self.slave,
            stdout=subprocess.DEVNULL,
            stderr=self.slave,
            process_group=0,
        )
        self.reader = threading.Thread(target=self._drain, daemon=True)
        self.reader.start()

    def _drain(self):
        while True:
            try:
                chunk = os.read(self.master, 65536)
            except OSError:
                return
            if not chunk:
                return
            self.output.extend(chunk)

    def wait_for(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise AssertionError(f"timed out; output tail: {bytes(self.output[-200:])!r}")
            time.sleep(0.02)

    def draws(self):
        return self.output.count(b"\x1b[?25l")

    def restores(self):
        return self.output.count(b"\x1b[?25h")

    def echo_enabled(self):
        return bool(termios.tcgetattr(self.slave)[3] & termios.ECHO)

    def child_alive(self):
        try:
            os.kill(int(self.pid_file.read_text()), 0)
        except ProcessLookupError:
            return False
        return True

    def finish(self, timeout=3):
        """Wait for macchiato to exit and collect the rest of its output."""
        status = self.process.wait(timeout=timeout)
        self.echo_after_exit = self.echo_enabled()
        self._close_slave()
        self.reader.join(timeout=2)
        return status

    def _close_slave(self):
        if self.slave >= 0:
            os.close(self.slave)
            self.slave = -1

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()
        if self.pid_file.exists() and self.child_alive():
            os.kill(int(self.pid_file.read_text()), signal.SIGKILL)
        self._close_slave()
        self.reader.join(timeout=2)
        os.close(self.master)
        self.directory.cleanup()


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
                self.assertEqual(process.wait(timeout=1), -signal.SIGINT)
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


    def test_utility_runs_without_animation_and_reads_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            child = fixture / "caffeinate"
            child.write_text("#!/bin/bash\n[[ $1 == -i ]] && shift\nexec \"$@\"\n")
            child.chmod(0o755)
            environment = os.environ.copy()
            environment["PATH"] = f"{fixture}:{environment['PATH']}"
            master, slave = os.openpty()
            try:
                result = subprocess.run(
                    [str(COMMAND), "-i", "cat"],
                    env=environment,
                    input=b"hola\n",
                    stdout=subprocess.PIPE,
                    stderr=slave,
                    timeout=5,
                )
                os.close(slave)
                slave = -1
                drawn = bytearray()
                while select.select([master], [], [], 0.1)[0]:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    drawn.extend(chunk)
            finally:
                if slave >= 0:
                    os.close(slave)
                os.close(master)

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b"hola\n")
            self.assertNotIn(b"\x1b[", drawn)

    def test_animates_only_without_a_utility(self):
        cases = {
            ("-t", "5"): True,
            ("-it5",): True,
            ("-d", "-w", "1"): True,
            ("-s", "--"): True,
            ("-i", "make"): False,
            ("--", "make"): False,
            ("-t", "5", "make", "-j4"): False,
        }
        for arguments, animates in cases.items():
            with self.subTest(arguments=arguments):
                session = TerminalSession("sleep 0.3\n", arguments)
                try:
                    self.assertEqual(session.finish(), 0)
                    self.assertEqual(session.draws() > 0, animates)
                finally:
                    session.close()

    def test_hangup_stops_caffeinate(self):
        session = TerminalSession("exec sleep 30\n")
        try:
            session.wait_for(lambda: session.draws() and session.pid_file.exists())
            session.process.send_signal(signal.SIGHUP)
            self.assertEqual(session.finish(), -signal.SIGHUP)
            session.wait_for(lambda: not session.child_alive())
        finally:
            session.close()

    def test_hides_typed_input_while_drawing(self):
        session = TerminalSession("sleep 0.6\n")
        try:
            self.assertTrue(session.echo_enabled())
            session.wait_for(session.draws)
            self.assertFalse(session.echo_enabled())
            self.assertEqual(session.finish(), 0)
            self.assertTrue(session.echo_after_exit)
        finally:
            session.close()

    def test_interrupt_restores_typed_input(self):
        session = TerminalSession("exec sleep 30\n")
        try:
            session.wait_for(lambda: session.draws() and session.pid_file.exists())
            session.process.send_signal(signal.SIGINT)
            self.assertEqual(session.finish(), -signal.SIGINT)
            self.assertTrue(session.echo_after_exit)
            self.assertTrue(session.output.endswith(b"\x1b[J\x1b[?25h"))
            self.assertFalse(session.child_alive())
        finally:
            session.close()

    def test_suspend_restores_terminal_and_redraws_on_resume(self):
        session = TerminalSession("sleep 2\n")
        try:
            session.wait_for(session.draws)
            session.process.send_signal(signal.SIGTSTP)
            _, status = os.waitpid(session.process.pid, os.WUNTRACED)
            self.assertTrue(os.WIFSTOPPED(status))
            session.wait_for(session.restores)
            self.assertTrue(session.echo_enabled())
            session.process.send_signal(signal.SIGCONT)
            session.wait_for(lambda: session.draws() >= 2)
            self.assertFalse(session.echo_enabled())
            self.assertEqual(session.finish(timeout=4), 0)
            self.assertTrue(session.echo_after_exit)
        finally:
            session.close()

if __name__ == "__main__":
    unittest.main()
