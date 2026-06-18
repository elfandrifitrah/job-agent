.PHONY: install install-dev install-all lint test test-quick test-all clean run-api run-dashboard

# ─── Installation ──────────────────────────────────────────────────────────

install:
	pip install -r requirements-base.txt

install-ai:
	pip install -r requirements-ai.txt

install-api:
	pip install -r requirements-api.txt

install-dev:
	pip install -r requirements-dev.txt

install-all:
	pip install -r requirements.txt

# ─── Linting ───────────────────────────────────────────────────────────────

lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --exit-zero --max-complexity=10 --max-line-length=120 --statistics

# ─── Testing ───────────────────────────────────────────────────────────────

test-quick:
	python -m pytest tests/test_cv_parser.py tests/test_api.py tests/test_matcher.py tests/test_db_models.py tests/test_cover_letter.py tests/test_cover_letter_api.py tests/test_auth_middleware.py -v --tb=short

test:
	python -m pytest tests/ -v --tb=short

test-slow:
	python -m pytest tests/ -v --tb=long -m slow

test-quick:
	python -m pytest tests/ -v --tb=short -m "not slow"

test-all:
	python -m pytest tests/ -v --tb=long

test-cov:
	python -m pytest tests/ --cov=backend --cov-report=term-missing --cov-report=html

# ─── API Server ────────────────────────────────────────────────────────────

run: run-api

run-api:
	@echo "  Dashboard: http://localhost:8000/dashboard"
	@echo "  API docs:  http://localhost:8000/docs"
	@echo ""
	uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

run-dashboard:
	cd dashboard && python -m http.server 3000

# ─── Database ──────────────────────────────────────────────────────────────

db-migrate:
	alembic upgrade head

db-revision:
	alembic revision --autogenerate -m "$(message)"

# ─── Utilities ─────────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	rm -rf .pytest_cache .coverage htmlcov

freeze:
	pip freeze | grep -v "^-e" > requirements.lock.txt
