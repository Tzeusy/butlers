.PHONY: lint format test test-unit test-integration test-core test-modules check

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

# Full test suite — runs all tests (both unit and integration)
test:
	uv run pytest -v

# Unit tests only — fast, no Docker required
test-unit:
	uv run pytest -m unit -v

# Integration tests only — requires Docker (testcontainers)
test-integration:
	uv run pytest -m integration -v

# Core component tests — tests/core/ directory
test-core:
	uv run pytest tests/core/ -v

# Module tests — tests/modules/ directory
test-modules:
	uv run pytest tests/modules/ -v

check: lint test
