"""What macchiato draws: layouts, colors, and redraws."""

import unittest

from helpers import BLOCK_GLYPHS, TerminalSession, run_in_terminal


def glyphs(output):
    return BLOCK_GLYPHS & set(output.decode())


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
