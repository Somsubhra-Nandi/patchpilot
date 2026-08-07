.PHONY: up down logs test test-api test-web lint build demo seed

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f api web

test: test-api test-web

test-api:
	cd apps/api && pytest

test-web:
	cd apps/web && pnpm test

lint:
	cd apps/api && ruff check patchpilot tests
	cd apps/web && pnpm lint

build:
	docker compose build

seed:
	docker compose exec api python -c "from patchpilot.demo.seed import seed_database; seed_database()"

demo:
	docker compose exec api python -m patchpilot.demo

