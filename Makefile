.PHONY: install verify lint format typecheck test arch api clean fresh-clone-check \
        migrate migrate-stamp migration migrate-status

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

# ---- Schema migrations (Alembic) ----
# Add or change a column? Don't wipe data/alion.db. Edit the SQLModel,
# then `make migration MSG="add foo to fighter"`, review the file under
# migrations/versions/, then `make migrate` to apply.

migrate:
	uv run alembic upgrade head

migrate-status:
	uv run alembic current

migration:
	@if [ -z "$(MSG)" ]; then echo "Usage: make migration MSG=\"short description\""; exit 1; fi
	uv run alembic revision --autogenerate -m "$(MSG)"

# Existing DB created by SQLModel.metadata.create_all() that pre-dates
# Alembic? Run this once to mark it as already at the baseline so
# subsequent `make migrate` calls only apply NEW migrations.
migrate-stamp:
	uv run alembic stamp head

# Simulates a fresh clone: wipe build artifacts, re-sync, re-verify.
# This is the "does it actually work on another machine" check.
fresh-clone-check:
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache **/__pycache__
	uv sync --extra dev
	$(MAKE) verify

clean:
	rm -rf .venv .pytest_cache .mypy_cache .ruff_cache dist build
	find . -type d -name __pycache__ -exec rm -rf {} +
