# Product brief

## Target user

People who use macOS `caffeinate` from a terminal and want an enjoyable, visible sign that it is still running.

## Core problem

`caffeinate` is silent while it runs, so an idle terminal gives no immediate visual indication that it remains active.

## Current alternative

Run `caffeinate` directly and inspect the process or wait for it to finish.

## Value proposition

Keep `caffeinate`'s behavior and arguments while showing a distinctive animated macchiato cup during execution.

## MVP hypothesis

A thin command-line wrapper that forwards arguments, animates only while `caffeinate` runs, and returns its exit status provides enough charm and visibility without changing the underlying utility.

## Core user journeys

- Run `macchiato` with any arguments accepted by `caffeinate`.
- See the cup animate in an interactive terminal until `caffeinate` exits or the user interrupts it.
- Run a utility through `caffeinate` (`macchiato -i make`) and have it behave exactly as with `caffeinate`: no drawing, and the utility keeps the terminal, its input, and its signals.
- Interrupt, suspend, or resize the terminal and find it restored afterward.
- Receive the same exit status and preserve the command's output.

## Non-goals

- Reimplementing macOS power assertions.
- Adding options that alter `caffeinate` behavior. The only arguments macchiato handles are `--version` and `--help`, and only on their own, since `caffeinate` rejects them. Preferences go in environment variables (`MACCHIATO_NO_ANIMATION`, `NO_COLOR`) that cannot collide with `caffeinate`'s arguments.
- Building a graphical interface.

## Success criteria

- Arguments reach `caffeinate` unchanged.
- Animation is present while the child runs and is cleaned up afterward.
- Noninteractive output, `TERM=dumb`, and utility runs have no animation or terminal control sequences.
- The wrapper returns `caffeinate`'s exit status. When interrupted or hung up, it stops `caffeinate`, restores the terminal, and terminates from the same signal.
- The cup degrades gracefully: 256 colors without true-color support, text only with `NO_COLOR` or in small windows.

## Product principles and constraints

- macOS only; delegate to the system `caffeinate` executable.
- Keep the wrapper a single file, free of additional runtime dependencies, and compatible with the system bash 3.2.
