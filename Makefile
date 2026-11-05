PREFIX ?= $(HOME)/.local
DESTDIR ?=
BINDIR = $(DESTDIR)$(PREFIX)/bin
MANDIR = $(DESTDIR)$(PREFIX)/share/man/man1
SHFMT = shfmt -i 2 -ci

.DEFAULT_GOAL := check
.PHONY: check test lint fmt snapshots install uninstall demo

check: lint test

test:
	python3 -m unittest discover -s tests -v

lint:
	bash -n bin/macchiato
	shellcheck bin/macchiato
	$(SHFMT) -d bin/macchiato
	ruff check tests
	ruff format --check tests
	actionlint
	mandoc -T lint -W warning man/macchiato.1

fmt:
	$(SHFMT) -w bin/macchiato
	ruff check --fix tests
	ruff format tests

# Accept intended changes to the drawing, then review the diff.
snapshots:
	UPDATE_SNAPSHOTS=1 python3 -m unittest discover -s tests -p 'test_snapshot.py'

install:
	install -d "$(BINDIR)" "$(MANDIR)"
	install -m 755 bin/macchiato "$(BINDIR)/macchiato"
	install -m 644 man/macchiato.1 "$(MANDIR)/macchiato.1"

uninstall:
	rm -f "$(BINDIR)/macchiato" "$(MANDIR)/macchiato.1"

demo:
	vhs docs/demo.tape
