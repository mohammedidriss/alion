.PHONY: install verify lint format typecheck test arch api clean fresh-clone-check \
        migrate migrate-stamp migration migrate-status \
        android-apk android-release ios-build

# ── Mobile builds ─────────────────────────────────────────────────────────────
ANDROID_HOME ?= $(HOME)/Library/Android/sdk
JAVA_HOME_21 ?= /opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
DASHBOARD     = apps/dashboard

# Debug APK — install directly on any Android device (no store account needed).
# Output: apps/dashboard/android/app/build/outputs/apk/debug/app-debug.apk
android-apk:
	cd $(DASHBOARD) && npx cap sync android
	cd $(DASHBOARD)/android && \
	  ANDROID_HOME=$(ANDROID_HOME) JAVA_HOME=$(JAVA_HOME_21) ./gradlew assembleDebug
	@echo ""
	@echo "✓ APK ready:"
	@ls -lh $(DASHBOARD)/android/app/build/outputs/apk/debug/app-debug.apk

# Release APK — requires KEYSTORE_PATH, KEYSTORE_PASS, KEY_ALIAS, KEY_PASS env vars.
android-release:
	cd $(DASHBOARD) && npx cap sync android
	cd $(DASHBOARD)/android && \
	  ANDROID_HOME=$(ANDROID_HOME) JAVA_HOME=$(JAVA_HOME_21) \
	  ./gradlew assembleRelease \
	    -Pandroid.injected.signing.store.file=$(KEYSTORE_PATH) \
	    -Pandroid.injected.signing.store.password=$(KEYSTORE_PASS) \
	    -Pandroid.injected.signing.key.alias=$(KEY_ALIAS) \
	    -Pandroid.injected.signing.key.password=$(KEY_PASS)
	@echo ""
	@echo "✓ Release APK ready:"
	@ls -lh $(DASHBOARD)/android/app/build/outputs/apk/release/app-release.apk

# iOS build — installs to connected device (id from: xcrun xctrace list devices).
DEVICE_ID ?= 00008140-000E31D13A29801C
ios-build:
	cd $(DASHBOARD) && npx cap sync ios
	xcodebuild \
	  -project $(DASHBOARD)/ios/App/App.xcodeproj \
	  -scheme App -configuration Debug \
	  -destination "id=$(DEVICE_ID)" \
	  -derivedDataPath /tmp/alion-build build
	xcrun devicectl device install app \
	  --device $(DEVICE_ID) \
	  /tmp/alion-build/Build/Products/Debug-iphoneos/App.app
	@echo "✓ Installed on device $(DEVICE_ID)"

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
