"""What macchiato draws: layouts, colors, and redraws."""

import os
import subprocess
import unittest

from helpers import BLOCK_GLYPHS, COMMAND, TerminalSession, run_in_terminal


def glyphs(output):
    return BLOCK_GLYPHS & set(output.decode())


def steam_lines(frames):
    """The steam macchiato draws for each of `frames`, computed without the cache.

    Runs the script's functions directly, so frames that take minutes to reach
    in a real run can be drawn at once. Returns (steam per frame, stderr).
    """
    script = COMMAND.read_text()
    self_call = 'main "$@"\n'
    assert script.endswith(self_call), "bin/macchiato no longer ends by calling main"
    driver = """
setup_colors
init_sine
layout
for frame in "$@"; do
  steam_cache=()
  draw_steam
  for ((i = 0; i < steam_lines; i++)); do
    printf '%s\\n' "${screen[i]}"
  done
  printf -- '--\\n'
done
"""
    env = os.environ.copy()
    env.pop("NO_COLOR", None)
    env["COLORTERM"] = "truecolor"
    result = subprocess.run(
        ["/bin/bash", "-c", script[: -len(self_call)] + driver, "macchiato", *map(str, frames)],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.stdout.split("--\n")[:-1], result.stderr


class AnimationTests(unittest.TestCase):
    def test_draws_cup_and_copy_then_restores_terminal(self):
        status, output = run_in_terminal(0.9)

        self.assertEqual(status, 0)
        self.assertTrue(glyphs(output), "cup is not drawn with block pixels")
        self.assertIn(b"\x1b[38;2;203;154;109m", output)
        self.assertIn(b"\x1b[48;2;70;50;37m", output)
        self.assertIn(b"Brewing some wakefulness", output)
        self.assertIn(b"Your Mac is staying awake", output)
        self.assertIn(b"Press Ctrl+C to finish your coffee", output)
        self.assertIn(b"\x1b[?25l", output)
        self.assertTrue(output.endswith(b"\x1b[J\x1b[?25h"), "drawing is not cleared on exit")

    def test_narrow_terminal_uses_compact_cup_and_copy(self):
        status, output = run_in_terminal(0.4, columns=32)

        text = output.decode()
        self.assertEqual(status, 0)
        self.assertTrue(glyphs(output), "compact cup is missing")
        self.assertIn("✓ \x1b[38;2;178;183;188mMac staying awake", text)
        self.assertNotIn("Press Ctrl+C to finish your coffee", text)

    def test_short_terminal_shows_copy_without_cup(self):
        status, output = run_in_terminal(0.4, rows=10)

        self.assertEqual(status, 0)
        self.assertFalse(glyphs(output), "cup does not fit a short terminal")
        self.assertIn(b"Your Mac is staying awake", output)
        self.assertTrue(output.endswith(b"\x1b[J\x1b[?25h"))

    def test_redraws_for_new_terminal_size(self):
        with TerminalSession("sleep 1.2\n") as session:
            session.wait_for(lambda: b"Your Mac is staying awake" in session.output)
            session.resize(32, 24)
            self.assertEqual(session.finish(), 0)
            before, _, after = session.output.decode().partition("\x1b[J")

        self.assertIn("Your Mac is staying awake", before)
        self.assertIn("Mac staying awake", after)
        self.assertNotIn("Your Mac is staying awake", after)

    def test_steam_after_a_long_run_repeats_the_first_cycle(self):
        # A resize clears the steam cache, so the steam is drawn again for the
        # current frame. After about seven minutes that frame number made a
        # sine index negative and every pixel printed "bad array subscript".
        cycle = list(range(14, 14 + 64))
        later = [frame + 64 * 200 for frame in cycle]

        steam, errors = steam_lines(cycle + later)

        self.assertEqual(errors, "")
        self.assertEqual(len(steam), 2 * len(cycle))
        self.assertTrue(all(glyphs(lines.encode()) for lines in steam), "steam is missing")
        self.assertEqual(steam[len(cycle) :], steam[: len(cycle)])

    def test_no_color_shows_plain_copy_without_cup(self):
        status, output = run_in_terminal(0.4, NO_COLOR="1")

        self.assertEqual(status, 0)
        self.assertFalse(glyphs(output))
        self.assertNotIn(b"\x1b[38;", output)
        self.assertNotIn(b"\x1b[48;", output)
        self.assertIn(b"Your Mac is staying awake", output)
        self.assertTrue(output.endswith(b"\x1b[J\x1b[?25h"))

    def test_falls_back_to_256_colors_without_truecolor(self):
        for colorterm in (None, "", "256color"):
            with self.subTest(COLORTERM=colorterm):
                status, output = run_in_terminal(0.4, COLORTERM=colorterm)

                self.assertEqual(status, 0)
                self.assertTrue(glyphs(output))
                self.assertIn(b"\x1b[38;5;173m", output)
                self.assertNotIn(b"\x1b[38;2;", output)
                self.assertNotIn(b"\x1b[48;2;", output)

    def test_accepts_24bit_as_truecolor(self):
        status, output = run_in_terminal(0.4, COLORTERM="24bit")

        self.assertEqual(status, 0)
        self.assertIn(b"\x1b[38;2;203;154;109m", output)


if __name__ == "__main__":
    unittest.main()
