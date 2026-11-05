# Contributing to macchiato

Thanks for helping. This guide covers reporting bugs, setting up a development environment, and how changes are released.

## Reporting bugs

Open an [issue](https://github.com/MauroCicerchia/macchiato/issues/new/choose). For problems with how the cup looks, include:

- your macOS version (`sw_vers -productVersion`);
- your terminal app and font;
- your window size (`stty size`);
- the output of `echo "$TERM $COLORTERM"`;
- a screenshot.

Report security issues privately, as described in [SECURITY.md](SECURITY.md).

## Development setup

You need macOS. Install the tools with Homebrew:

```sh
brew install python@3.13 shellcheck shfmt ruff actionlint vhs
```

- Python 3.11 or later runs the tests. They use only the standard library.
- [ShellCheck](https://www.shellcheck.net) and [shfmt](https://github.com/mvdan/sh) lint and format the script.
- [Ruff](https://docs.astral.sh/ruff/) lints and formats the tests.
- [actionlint](https://github.com/rhysd/actionlint) checks the GitHub workflows.
- `mandoc`, which ships with macOS, checks the man page.
- [VHS](https://github.com/charmbracelet/vhs) records the demo GIF; it is only needed for `make demo`.

## Everyday commands

```sh
make            # lint and test (same as make check)
make fmt        # format the script and the tests
make snapshots  # accept an intended change to the drawing
make demo       # re-record docs/demo.gif
make install    # install into ~/.local (PREFIX=... to change)
```

CI runs `make lint` and `make test` on macOS for every pull request.

## Code guidelines

- **Keep the wrapper thin.** Every argument goes to `caffeinate` unchanged. macchiato must not change how the Mac stays awake. `--version` and `--help` are the only arguments it handles, and only on their own. See [docs/product.md](docs/product.md).
- **Write for bash 3.2.** `bin/macchiato` runs on the bash that ships with macOS, so avoid associative arrays, `mapfile`, `${var^^}`, fractional `read -t`, and `source <(...)`. CI runs the tests with that bash.
- **Keep it a single file** with no runtime dependencies, so installing it means copying one script.
- **Test on a pseudo-terminal.** Use `TerminalSession` and `run_in_terminal` in `tests/helpers.py`. They keep reading the terminal output: a test that stops reading can block the script and make signals look broken.
- **Review drawing changes.** Geometry or color changes alter `tests/snapshots/*.txt`. Run `make snapshots` and check the diff. Include a screenshot or GIF in the pull request.

## Commits and releases

Pull requests are squash-merged, and the pull request title becomes the commit message. Titles must follow [Conventional Commits](https://www.conventionalcommits.org), which a CI check enforces. For example:

- `feat: …` for a new feature (minor version)
- `fix: …` for a bug fix (patch version)
- `docs: …`, `test: …`, `ci: …`, `build: …`, or `chore: …` for everything else (no release)

[release-please](https://github.com/googleapis/release-please) reads those commits and keeps a release pull request open. Merging it:

1. updates `CHANGELOG.md`, `version.txt`, and the version in `bin/macchiato`;
2. tags the release and publishes it on GitHub;
3. updates the formula in [MauroCicerchia/homebrew-tap](https://github.com/MauroCicerchia/homebrew-tap).

The release workflow uses the `RELEASE_TOKEN` Actions secret. It is a fine-grained token with Contents and Pull requests read/write on both repositories, and Issues read/write on this one. With it, CI runs on release pull requests and the workflow can push the formula update.
