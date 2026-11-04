# Every recipe line is a `docker compose` command, so this works under cmd.exe or sh.
# One-off commands use `run --rm --no-deps` unless they need Postgres/Valkey.

.PHONY: dev down lint test-backend test-frontend licenses test

dev:
	docker compose up --build

down:
	docker compose down

lint:
	docker compose run --rm --no-deps backend ruff check .
	docker compose run --rm --no-deps backend black --check .
	docker compose run --rm --no-deps frontend npm run lint
	docker compose run --rm --no-deps frontend npm run format:check
	docker compose run --rm --no-deps frontend npm run typecheck

test-backend:
	docker compose run --rm backend pytest -q

test-frontend:
	docker compose run --rm --no-deps frontend npx vitest run --reporter=dot

licenses:
	docker compose run --rm --no-deps backend python scripts/check_licenses.py
	docker compose run --rm --no-deps frontend node scripts/check-licenses.mjs

test: lint test-backend test-frontend licenses
