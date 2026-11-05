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
- Receive the same exit status and preserve the command's output.

## Non-goals

- Reimplementing macOS power assertions.
- Adding options that alter `caffeinate` behavior.
- Building a graphical interface.

## Success criteria

- Arguments reach `caffeinate` unchanged.
- Animation is present while the child runs and is cleaned up afterward.
- Noninteractive output has no animation or terminal control sequences.
- The wrapper returns `caffeinate`'s exit status.

## Product principles and constraints

- macOS only; delegate to the system `caffeinate` executable.
- Keep the wrapper small and free of additional runtime dependencies.
