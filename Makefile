.PHONY: test test-unit test-integration test-gmail test-all install-test

install-test:
	pip install -r requirements-test.txt

# Fast — no LLM, no external services
test-unit:
	pytest tests/ -m "unit" -v

# Requires LLM provider running (set LLM_PROVIDER in .env)
test-integration:
	pytest tests/ -m "integration" -v -s

# Requires Gmail token files in credentials/
test-gmail:
	pytest tests/ -m "gmail" -v -s

# Everything
test-all:
	pytest tests/ -v -s

# Default: run unit tests
test: test-unit
