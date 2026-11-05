# macchiato

A thin macOS wrapper around `caffeinate`, with an animated, coffee-colored terminal cup while it runs.

## Install

Copy the executable into a directory on your `PATH`:

```sh
mkdir -p ~/.local/bin
cp bin/macchiato ~/.local/bin/macchiato
```

Add `~/.local/bin` to your `PATH` if it is not already there.

## Use

```sh
macchiato -t 3600
macchiato -i -w 12345
macchiato
```

Every argument goes directly to `caffeinate`. A pixel-art cup with rising steam animates on an interactive terminal's standard error until `caffeinate` exits, scaled to fit the window. Typed keys are not echoed while the cup is drawn, and `Ctrl+Z` clears the drawing until you resume with `fg`. Press `Ctrl+C` to stop.

`macchiato` returns the child's exit status when it finishes normally. When interrupted or hung up, it stops `caffeinate`, restores the terminal, and exits from the same signal, so shell loops and scripts stop as they would with `caffeinate`.

When standard error is redirected, or when `caffeinate` runs a utility (`macchiato -i make`), nothing is drawn: `macchiato` hands the process over to `caffeinate`, so the utility keeps the terminal, its input, and its signals.

## Develop

Requires macOS, Python 3 for tests, and ShellCheck for linting. No additional runtime dependencies are needed.

```sh
make test
make lint
```
