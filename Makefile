.PHONY: test lint

test:
	python3 -m unittest discover -s tests -v

lint:
	bash -n bin/macchiato
	shellcheck bin/macchiato
	python3 -m py_compile tests/test_macchiato.py
