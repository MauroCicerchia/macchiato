"""Interrupts, hangups, suspension, and the terminal state around them."""

import os
import signal
import unittest

from helpers import TerminalSession


class SignalTests(unittest.TestCase):
    def test_interrupt_stops_caffeinate_and_restores_terminal(self):
        with TerminalSession("exec sleep 30\n") as session:
            session.wait_for(lambda: session.draws() and session.pid_file.exists())
            session.process.send_signal(signal.SIGINT)

            self.assertEqual(session.finish(), -signal.SIGINT)
            self.assertTrue(session.echo_after_exit)
            self.assertTrue(session.output.endswith(b"\x1b[J\x1b[?25h"))
            self.assertFalse(session.child_alive())

    def test_terminate_stops_caffeinate(self):
        with TerminalSession("exec sleep 30\n") as session:
            session.wait_for(lambda: session.draws() and session.pid_file.exists())
            session.process.send_signal(signal.SIGTERM)

            self.assertEqual(session.finish(), -signal.SIGTERM)
            session.wait_for(lambda: not session.child_alive())

    def test_hangup_stops_caffeinate(self):
        with TerminalSession("exec sleep 30\n") as session:
            session.wait_for(lambda: session.draws() and session.pid_file.exists())
            session.process.send_signal(signal.SIGHUP)

            self.assertEqual(session.finish(), -signal.SIGHUP)
            session.wait_for(lambda: not session.child_alive())

    def test_hides_typed_input_while_drawing(self):
        with TerminalSession("sleep 0.6\n") as session:
            self.assertTrue(session.echo_enabled())
            session.wait_for(session.draws)
            self.assertFalse(session.echo_enabled())

            self.assertEqual(session.finish(), 0)
            self.assertTrue(session.echo_after_exit)

    def test_suspend_restores_terminal_and_redraws_on_resume(self):
        with TerminalSession("sleep 2\n") as session:
            session.wait_for(session.draws)
            session.process.send_signal(signal.SIGTSTP)
            _, status = os.waitpid(session.process.pid, os.WUNTRACED)
            self.assertTrue(os.WIFSTOPPED(status))
            session.wait_for(session.restores)
            self.assertTrue(session.echo_enabled())

            session.process.send_signal(signal.SIGCONT)
            session.wait_for(lambda: session.draws() >= 2)
            self.assertFalse(session.echo_enabled())
            self.assertEqual(session.finish(), 0)
            self.assertTrue(session.echo_after_exit)


if __name__ == "__main__":
    unittest.main()
