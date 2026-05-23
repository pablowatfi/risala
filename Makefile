.PHONY: test test-unit test-integration test-gmail test-all install-test

install-test:
	pip3 install -r requirements-test.txt

# Fast — no LLM, no external services
test-unit:
	.venv/bin/pytest tests/ -m "unit" -v

# Requires LLM provider running (set LLM_PROVIDER in .env)
test-integration:
	.venv/bin/pytest tests/ -m "integration" -v -s

# Requires Gmail token files in credentials/
test-gmail:
	.venv/bin/pytest tests/ -m "gmail" -v -s

# Everything
test-all:
	.venv/bin/pytest tests/ -v -s

# Default: run unit tests
test: test-unit
