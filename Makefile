PY := .venv/Scripts/python.exe
SEED ?= 1729

# Convenience wrapper for Unix and CI. The documented, cross-platform path is
#   python -m praman <command>
# because `make` is not present on a stock Windows machine.

.PHONY: install test lint demo clean

install:
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -e ".[dev]"

test:
	$(PY) -m praman test

lint:
	$(PY) -m praman lint

demo:
	$(PY) -m praman demo --seed $(SEED)

clean:
	rm -rf *.db .pytest_cache .ruff_cache
