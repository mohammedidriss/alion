.PHONY: install verify lint format typecheck test arch api clean fresh-clone-check

install:
	uv sync --extra dev

verify: lint typecheck arch test
	@echo "✓ All checks passed"

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy packages

arch:
	uv run lint-imports

test:
	uv run pytest -v

api:
	uv run uvicorn api.main:app --reload

# Simulates a fresh clone: wipe build artifacts, re-sync, re-verify.
# This is the "does it actually work on another machine" check.
fresh-clone-check:
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache **/__pycache__
	uv sync --extra dev
	$(MAKE) verify

clean:
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
