# Macchiato

Read `docs/product.md` for the approved product direction, `README.md` for the CLI usage, and `CONTRIBUTING.md` for the development workflow.

- Keep the wrapper thin: forward `caffeinate` arguments unchanged and leave macOS power behavior to `caffeinate`. `--version` and `--help` are the only arguments macchiato handles, and only on their own.
- `bin/macchiato` must stay a single file that runs on macOS `/bin/bash` 3.2: no associative arrays, `mapfile`, `${var^^}`, fractional `read -t`, `BASH_XTRACEFD`, or `source <(...)`.
- Run `make check` (lint and tests) before committing. Use Conventional Commits, one commit per topic.
- Tests that use a pseudo-terminal must keep draining its output. Use `TerminalSession` or `run_in_terminal` from `tests/helpers.py`; a pty nobody reads blocks the script and makes signal tests hang.
- Drawing changes update `tests/snapshots/`; run `make snapshots` and review the diff.
- Keep transient plans and notes in `.context/`.
