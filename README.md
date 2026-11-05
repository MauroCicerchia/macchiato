# macchiato

Keep your Mac awake with a little coffee. **macchiato** is a macOS command-line wrapper around the system's `caffeinate` utility. It passes your arguments through unchanged and shows an animated cup while `caffeinate` runs in an interactive terminal.

The cup stays out of the way when you run a command through `caffeinate` or redirect standard error.

## Quick start

On macOS, clone the repository and try it without installing anything:

```sh
git clone https://github.com/MauroCicerchia/macchiato.git
cd macchiato
./bin/macchiato -t 10
```

The cup should animate for ten seconds. Run `./bin/macchiato` without a timeout to keep your Mac awake until you press `Ctrl+C`.

## Install

### Homebrew

Once the first release is published, install macchiato from the [personal tap](https://github.com/MauroCicerchia/homebrew-tap):

```sh
brew install maurocicerchia/tap/macchiato
```

Homebrew handles later upgrades and removal:

```sh
brew upgrade macchiato
brew uninstall macchiato
```

### From source

Alternatively, copy the script into a directory on your `PATH`:

```sh
mkdir -p "$HOME/.local/bin"
install -m 755 bin/macchiato "$HOME/.local/bin/macchiato"
export PATH="$HOME/.local/bin:$PATH"
```

The `export` line affects the current shell. Add it to your shell startup file (for example, `~/.zshrc`) to use `macchiato` in future terminals.

macchiato requires macOS and its built-in `caffeinate` and `/bin/bash`. The animation looks best in a terminal with ANSI true-color support. There are no third-party runtime dependencies.

## Usage

```sh
macchiato                 # Stay awake until Ctrl+C
macchiato -t 3600         # Stay awake for one hour
macchiato -d -t 1800      # Keep the display awake for 30 minutes
macchiato -w 12345        # Stay awake until process 12345 exits
macchiato -i make         # Keep awake while make runs
```

All options belong to `caffeinate`; macchiato adds none. Run `man caffeinate` for the full list of flags and their behavior.

### Terminal behavior

- With no utility command and an interactive standard error, macchiato draws the cup, resizing it to fit the terminal. It hides typed input while drawing and restores the terminal when it finishes.
- `Ctrl+C` stops `caffeinate` and the wrapper. `Ctrl+Z` clears the drawing and suspends it; `fg` resumes the animation.
- When a utility is supplied (such as `make`) or standard error is redirected, macchiato runs `caffeinate` directly without animation. The utility keeps its input, output, and signals.
- When `caffeinate` exits normally, macchiato returns its exit status. On interruption or hangup, it stops `caffeinate`, restores the terminal, and terminates from the same signal.

## Development and contributions

Bug reports and ideas are welcome in [GitHub Issues](https://github.com/MauroCicerchia/macchiato/issues). For a pull request, run the checks below and describe the change. For animation issues, include your macOS version, terminal app, and window size.

Tests need Python 3; linting needs [ShellCheck](https://www.shellcheck.net/). CI runs both checks on macOS.

```sh
make test
make lint
```

### Releases

Commits on `main` follow [Conventional Commits](https://www.conventionalcommits.org/). [release-please](https://github.com/googleapis/release-please) opens a release pull request from those commits. Merging that pull request adds `version.txt` and `CHANGELOG.md`, creates the version tag and GitHub release, and updates the formula in the Homebrew tap. Maintainers configure the `RELEASE_TOKEN` Actions secret to let release pull requests run CI and update the tap.

## License

macchiato is available under the [MIT License](LICENSE).
