.PHONY: setup dev api web demo format lint typecheck test test-web test-e2e build-web check security clean

UV ?= uv
NPM ?= npm

setup:
	$(UV) sync --all-extras
	cd web && $(NPM) ci

dev:
	@trap 'kill 0' INT TERM EXIT; $(UV) run uvicorn chna_extractor.api:app --reload --port 8000 & cd web && $(NPM) run dev

api:
	$(UV) run uvicorn chna_extractor.api:app --reload --port 8000

web:
	cd web && $(NPM) run dev

demo:
	$(UV) run chna demo --output demo-result.json

format:
	$(UV) run ruff format src tests scripts
	$(UV) run ruff check --fix src tests scripts

lint:
	$(UV) run ruff format --check src tests scripts
	$(UV) run ruff check src tests scripts
	cd web && $(NPM) run lint

typecheck:
	$(UV) run mypy src
	cd web && $(NPM) run typecheck

test:
	$(UV) run pytest

test-web:
	cd web && $(NPM) test -- --run

test-e2e:
	cd web && $(NPM) run test:e2e

build-web:
	cd web && $(NPM) run build

check: lint typecheck test test-web build-web

security:
	mkdir -p .data
	$(UV) export --frozen --all-extras --no-emit-project --format requirements-txt --output-file .data/audit-requirements.txt
	$(UV) run --with pip-audit pip-audit -r .data/audit-requirements.txt
	cd web && $(NPM) audit --audit-level=high
	$(UV) run pre-commit run gitleaks --all-files

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .data .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml web/dist web/coverage
