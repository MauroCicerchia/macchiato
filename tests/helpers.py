"""Shared fixtures for macchiato's tests.

macchiato draws on a terminal, so most tests run it on a pseudo-terminal with
a stand-in `caffeinate` placed first on PATH. Output from a pty must always be
drained: if nobody reads it, the script blocks on write and stops responding
to signals.
"""

import fcntl
import os
import re
import signal
import struct
import subprocess
import tempfile
import termios
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMAND = ROOT / "bin" / "macchiato"
BLOCK_GLYPHS = set("▘▝▖▗▀▄▌▐▚▞▙▛▜▟█")
FRAME_END = b"\x1b[?2026l"


def fake_caffeinate(directory, script):
    """Write a bash stand-in for caffeinate that records its pid, then runs `script`."""
    child = Path(directory) / "caffeinate"
    child.write_text('#!/bin/bash\necho "$$" > "$MACCHIATO_PID_FILE"\n' + script)
    child.chmod(0o755)
    return child


def environment(directory, **overrides):
    """An environment that finds the stand-in caffeinate and can draw in 24-bit color.

    Variables the user may have set (NO_COLOR, MACCHIATO_NO_ANIMATION) are removed
    so they cannot change test results. Pass a value of None to unset a variable.
    """
    env = os.environ.copy()
    for name in ("NO_COLOR", "MACCHIATO_NO_ANIMATION"):
        env.pop(name, None)
    env["PATH"] = f"{directory}:{env['PATH']}"
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env["MACCHIATO_PID_FILE"] = str(Path(directory) / "pid")
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return env


def set_size(fd, columns, rows):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))


class TerminalSession:
    """macchiato on a pseudo-terminal used as stdin and stderr, as a shell runs it."""

    def __init__(self, child_script, arguments=(), columns=80, rows=24, **env):
        self.directory = tempfile.TemporaryDirectory()
        fake_caffeinate(self.directory.name, child_script)
        self.pid_file = Path(self.directory.name) / "pid"
        self.master, self.slave = os.openpty()
        set_size(self.slave, columns, rows)
        self.output = bytearray()
        self.echo_after_exit = None
        self.process = subprocess.Popen(
            [str(COMMAND), *arguments],
            env=environment(self.directory.name, **env),
            stdin=self.slave,
            stdout=subprocess.DEVNULL,
            stderr=self.slave,
            # A process group of its own, whose parent is in the same session, can
            # be stopped by job-control signals.
            process_group=0,
        )
        self.reader = threading.Thread(target=self._drain, daemon=True)
        self.reader.start()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _drain(self):
        while True:
            try:
                chunk = os.read(self.master, 65536)
            except OSError:
                return
            if not chunk:
                return
            self.output.extend(chunk)

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise AssertionError(f"timed out; output tail: {bytes(self.output[-200:])!r}")
            time.sleep(0.02)

    def resize(self, columns, rows):
        set_size(self.slave, columns, rows)
        self.process.send_signal(signal.SIGWINCH)

    def draws(self):
        return self.output.count(b"\x1b[?25l")

    def restores(self):
        return self.output.count(b"\x1b[?25h")

    def frames(self):
        return self.output.count(FRAME_END)

    def echo_enabled(self):
        return bool(termios.tcgetattr(self.slave)[3] & termios.ECHO)

    def child_alive(self):
        try:
            os.kill(int(self.pid_file.read_text()), 0)
        except ProcessLookupError:
            return False
        return True

    def finish(self, timeout=5):
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


def run_in_terminal(child_seconds=0.6, arguments=(), columns=80, rows=24, **env):
    """Run macchiato until the stand-in caffeinate exits; return (status, output)."""
    with TerminalSession(f"sleep {child_seconds}\n", arguments, columns, rows, **env) as session:
        status = session.finish(timeout=child_seconds + 5)
        return status, bytes(session.output)


SEQUENCE = re.compile(r"\x1b\[([?0-9;]*)([A-Za-z])")


class Screen:
    """Replay the escape sequences macchiato emits into a grid of styled cells.

    Supports only what the script writes: SGR colors, cursor up/down, erase in
    line and display, carriage return, and line feed.
    """

    def __init__(self, columns, rows):
        self.columns, self.rows = columns, rows
        self.cells = [[(" ", None, None) for _ in range(columns)] for _ in range(rows)]
        self.x = self.y = 0
        self.fg = self.bg = None

    def feed(self, data):
        text = data.decode()
        position = 0
        while position < len(text):
            if text[position] == "\x1b":
                match = SEQUENCE.match(text, position)
                params, command = match.group(1), match.group(2)
                position = match.end()
                if not params.startswith("?"):
                    self._control(params, command)
                continue
            self._put(text[position])
            position += 1

    def _control(self, params, command):
        numbers = [int(n) if n else 0 for n in params.split(";")] if params else []
        count = numbers[0] if numbers and numbers[0] else 1
        if command == "A":
            self.y = max(0, self.y - count)
        elif command == "B":
            self.y = min(self.rows - 1, self.y + count)
        elif command == "K":
            for x in range(self.x, self.columns):
                self.cells[self.y][x] = (" ", None, None)
        elif command == "J":
            for x in range(self.x, self.columns):
                self.cells[self.y][x] = (" ", None, None)
            for y in range(self.y + 1, self.rows):
                self.cells[y] = [(" ", None, None) for _ in range(self.columns)]
        elif command == "m":
            self._style(numbers or [0])

    def _style(self, numbers):
        index = 0
        while index < len(numbers):
            code = numbers[index]
            if code == 0:
                self.fg = self.bg = None
            elif code == 39:
                self.fg = None
            elif code == 49:
                self.bg = None
            elif code in (38, 48):
                if numbers[index + 1] == 2:
                    color = ";".join(str(n) for n in numbers[index + 2 : index + 5])
                    index += 4
                else:
                    color = f"@{numbers[index + 2]}"
                    index += 2
                if code == 38:
                    self.fg = color
                else:
                    self.bg = color
            index += 1

    def _put(self, character):
        if character == "\r":
            self.x = 0
        elif character == "\n":
            self.y += 1
            if self.y >= self.rows:
                self.cells.pop(0)
                self.cells.append([(" ", None, None) for _ in range(self.columns)])
                self.y = self.rows - 1
        else:
            if self.x < self.columns:
                self.cells[self.y][self.x] = (character, self.fg, self.bg)
            self.x += 1

    def text(self):
        return "\n".join("".join(cell[0] for cell in row).rstrip() for row in self.cells).rstrip()

    def dump(self):
        """A readable snapshot: the glyphs, a style letter per cell, and the legend."""
        styles = {}
        glyph_rows, style_rows = [], []
        for row in self.cells:
            glyph_rows.append("".join(cell[0] for cell in row).rstrip())
            letters = []
            for _, fg, bg in row:
                key = (fg, bg)
                if key == (None, None):
                    letters.append(".")
                    continue
                if key not in styles:
                    styles[key] = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"[len(styles)]
                letters.append(styles[key])
            style_rows.append("".join(letters).rstrip("."))
        while glyph_rows and not glyph_rows[-1] and not style_rows[-1]:
            glyph_rows.pop()
            style_rows.pop()
        legend = [
            f"{letter} fg={fg or 'default'} bg={bg or 'default'}" for (fg, bg), letter in styles.items()
        ]
        return (
            "\n".join(
                ["[glyphs]", *glyph_rows, "[styles]", *style_rows[: len(glyph_rows)], "[legend]", *legend]
            )
            + "\n"
        )


def screen_after(output, frames, columns, rows):
    """The screen after replaying the first `frames` frames of `output`."""
    screen = Screen(columns, rows)
    chunks = bytes(output).split(FRAME_END)
    screen.feed(FRAME_END.join(chunks[:frames]) + FRAME_END)
    return screen
