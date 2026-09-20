.PHONY: dev migrate lint typecheck test test-backend test-frontend test-integration test-e2e test-version

dev:
	docker compose up --build

migrate:
	docker compose exec api .venv/bin/alembic upgrade head

lint:
	cd server && uv run ruff check app tests
	cd client && npm run lint

typecheck:
	cd server && uv run mypy app
	cd client && npm run typecheck

test-backend:
	cd server && uv run pytest

test-frontend:
	cd client && npm run test

test-integration:
	cd server && uv run pytest -m integration

test-e2e:
	cd client && npm run test:e2e

test: lint typecheck test-backend test-frontend

test-version:
	@if [ "$(VERSION)" != "0.1" ] && [ "$(VERSION)" != "0.2" ] && [ "$(VERSION)" != "0.3" ] && [ "$(VERSION)" != "0.4" ] && [ "$(VERSION)" != "0.5" ] && [ "$(VERSION)" != "0.6" ] && [ "$(VERSION)" != "0.7" ] && [ "$(VERSION)" != "0.8" ] && [ "$(VERSION)" != "0.9" ] && [ "$(VERSION)" != "1.0" ]; then echo "Unsupported VERSION=$(VERSION)"; exit 2; fi
	docker compose config --quiet
	$(MAKE) test
	cd client && npm run build
	$(MAKE) test-e2e
