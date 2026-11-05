"""Arguments, output, status, and the cases where macchiato hands over to caffeinate."""

import json
import os
import select
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import COMMAND, ROOT, environment, run_in_terminal


def read_all(master):
    output = bytearray()
    while select.select([master], [], [], 0.1)[0]:
        try:
            chunk = os.read(master, 65536)
        except OSError:
            break
        if not chunk:
            break
        output.extend(chunk)
    return bytes(output)


class PassthroughTests(unittest.TestCase):
    def test_forwards_arguments_output_and_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            child = Path(directory) / "caffeinate"
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
            args_file = Path(directory) / "args.json"
            result = subprocess.run(
                [str(COMMAND), "-t", "5", "spaced argument", ""],
                env=environment(directory, MACCHIATO_ARGS_FILE=str(args_file)),
                capture_output=True,
                text=True,
                timeout=5,
            )
            arguments = json.loads(args_file.read_text())

        self.assertEqual(arguments, ["-t", "5", "spaced argument", ""])
        self.assertEqual(result.returncode, 23)
        self.assertEqual(result.stdout, "child stdout\n")
        self.assertEqual(result.stderr, "child stderr\n")

    def test_utility_runs_without_animation_and_reads_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            child = Path(directory) / "caffeinate"
            child.write_text('#!/bin/bash\n[[ $1 == -i ]] && shift\nexec "$@"\n')
            child.chmod(0o755)
            master, slave = os.openpty()
            try:
                result = subprocess.run(
                    [str(COMMAND), "-i", "cat"],
                    env=environment(directory),
                    input=b"hola\n",
                    stdout=subprocess.PIPE,
                    stderr=slave,
                    timeout=5,
                )
                os.close(slave)
                slave = -1
                drawn = read_all(master)
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
            ("-ti", "5"): False,  # getopt reads "i" as the timeout, so "5" is a utility
        }
        for arguments, animates in cases.items():
            with self.subTest(arguments=arguments):
                status, output = run_in_terminal(0.3, arguments)
                self.assertEqual(status, 0)
                self.assertEqual(b"\x1b[?25l" in output, animates)

    def test_terminals_that_cannot_draw_get_plain_caffeinate(self):
        cases = {
            "TERM=dumb": {"TERM": "dumb"},
            "TERM unset": {"TERM": None},
            "MACCHIATO_NO_ANIMATION=1": {"MACCHIATO_NO_ANIMATION": "1"},
        }
        for name, env in cases.items():
            with self.subTest(name):
                status, output = run_in_terminal(0.3, **env)
                self.assertEqual(status, 0)
                self.assertNotIn(b"\x1b[", output)

    def test_version_matches_the_release_manifest(self):
        manifest = json.loads((ROOT / ".release-please-manifest.json").read_text())
        result = subprocess.run([str(COMMAND), "--version"], capture_output=True, text=True, timeout=5)

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, f"macchiato {manifest['.']}\n")

    def test_help_describes_usage_and_environment(self):
        result = subprocess.run([str(COMMAND), "--help"], capture_output=True, text=True, timeout=5)

        self.assertEqual(result.returncode, 0)
        self.assertIn("Usage: macchiato [caffeinate options]", result.stdout)
        for name in ("MACCHIATO_NO_ANIMATION", "NO_COLOR", "COLORTERM", "man caffeinate"):
            self.assertIn(name, result.stdout)

    def test_version_and_help_with_other_arguments_go_to_caffeinate(self):
        with tempfile.TemporaryDirectory() as directory:
            child = Path(directory) / "caffeinate"
            child.write_text('#!/bin/bash\nprintf "%s\\n" "$@"\nexit 1\n')
            child.chmod(0o755)
            for arguments in (["--version", "-t", "1"], ["-t", "1", "--help"]):
                with self.subTest(arguments=arguments):
                    result = subprocess.run(
                        [str(COMMAND), *arguments],
                        env=environment(directory),
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stdout.split(), arguments)


if __name__ == "__main__":
    unittest.main()
