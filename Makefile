# Every recipe line is a `docker compose` command, so this works under cmd.exe or sh.
# One-off commands use `run --rm --no-deps` unless they need Postgres/Valkey.

.PHONY: dev down lint types types-check test-backend test-frontend licenses test seed

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
	$(MAKE) types-check

types:
	docker compose run --rm --no-deps backend python manage.py spectacular --file /app/schema.yml --validate
	docker compose run --rm --no-deps frontend npx openapi-typescript /schema/schema.yml -o src/lib/api-schema.d.ts

# Fails if the committed schema or generated types are stale (compares against regenerated output in temp files).
types-check:
	docker compose run --rm --no-deps backend sh -c "python manage.py spectacular --file /tmp/schema.yml && diff /app/schema.yml /tmp/schema.yml"
	docker compose run --rm --no-deps frontend sh -c "npx openapi-typescript /schema/schema.yml -o /tmp/api-schema.d.ts && diff src/lib/api-schema.d.ts /tmp/api-schema.d.ts"
seed:
	docker compose run --rm backend python manage.py seed_pilot

test-backend:
	docker compose run --rm backend pytest -q

test-frontend:
	docker compose run --rm --no-deps frontend npx vitest run --reporter=dot

licenses:
	docker compose run --rm --no-deps backend python scripts/check_licenses.py
	docker compose run --rm --no-deps frontend node scripts/check-licenses.mjs

test: lint test-backend test-frontend licenses
