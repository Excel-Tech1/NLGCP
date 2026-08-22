.PHONY: setup up down test lint typecheck build check health api web clean

PYTHON := .venv/bin/python

setup:
	bash scripts/bootstrap.sh

up:
	docker compose up -d --build

down:
	docker compose down

test:
	$(PYTHON) -m pytest
	cd services/gnss-ingestor && go test ./...
	cmake -S services/nrtk-engine -B build/nrtk-engine
	cmake --build build/nrtk-engine
	ctest --test-dir build/nrtk-engine --output-on-failure

lint:
	$(PYTHON) -m ruff check .
	cd services/gnss-ingestor && gofmt -d . && go vet ./...
	npm --prefix apps/web run lint

typecheck:
	$(PYTHON) -m mypy
	npm --prefix apps/web run typecheck

build:
	cmake -S services/nrtk-engine -B build/nrtk-engine
	cmake --build build/nrtk-engine
	npm --prefix apps/web run build

check: lint typecheck test build

health:
	bash scripts/health-check.sh

api:
	$(PYTHON) -m uvicorn nlgcp_api.main:app --reload

web:
	npm --prefix apps/web run dev

clean:
	cmake --build build/nrtk-engine --target clean 2>/dev/null || true
	rm -rf apps/web/.next
