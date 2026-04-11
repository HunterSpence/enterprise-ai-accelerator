# AIAuditTrail v2.0 — Makefile
# Usage: make <target>

.DEFAULT_GOAL := help
.PHONY: help install demo ui api benchmark test lint type-check coverage docker-up docker-down clean

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
help:
	@echo ""
	@echo "AIAuditTrail v2.0 — Available commands:"
	@echo ""
	@echo "  make demo        Run the CLI demo (no API key needed)"
	@echo "  make ui          Launch Streamlit compliance dashboard"
	@echo "  make api         Start FastAPI server (localhost:8000)"
	@echo "  make benchmark   Show competitive compliance benchmark"
	@echo "  make test        Run full test suite"
	@echo "  make coverage    Run tests with coverage report"
	@echo "  make lint        Run ruff linter"
	@echo "  make type-check  Run mypy type checker"
	@echo "  make docker-up   Start Docker Compose (API + Redis)"
	@echo "  make docker-down Stop Docker Compose"
	@echo "  make install     Install with all optional dependencies"
	@echo "  make clean       Remove .pyc, __pycache__, .db files"
	@echo ""

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
install:
	pip install -e ".[all]"

install-core:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

# ---------------------------------------------------------------------------
# Run targets
# ---------------------------------------------------------------------------
demo:
	@echo "Running AIAuditTrail CLI demo..."
	python -m ai_audit_trail.demo

ui:
	@echo "Launching Streamlit compliance dashboard..."
	streamlit run web_ui.py --server.port 8501

api:
	@echo "Starting FastAPI server at http://localhost:8000..."
	@echo "API docs: http://localhost:8000/docs"
	uvicorn ai_audit_trail.api:app --host 0.0.0.0 --port 8000 --reload

benchmark:
	@echo "Running compliance benchmark..."
	python benchmark.py

sdk-demo-anthropic:
	python sdk_examples/01_anthropic_quickstart.py

sdk-demo-openai:
	python sdk_examples/02_openai_quickstart.py

sdk-demo-langchain:
	python sdk_examples/03_langchain_chain.py

sdk-demo-llamaindex:
	python sdk_examples/04_llamaindex_rag.py

sdk-demo-crewai:
	python sdk_examples/05_crewai_agents.py

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------
test:
	pytest tests/ -v --tb=short

test-chain:
	pytest tests/test_chain.py -v

test-eu-ai-act:
	pytest tests/test_eu_ai_act.py -v

test-incidents:
	pytest tests/test_incident_manager.py -v

test-integrations:
	pytest tests/test_integrations.py -v

coverage:
	coverage run -m pytest tests/
	coverage report -m
	coverage html
	@echo "HTML coverage report: htmlcov/index.html"

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------
lint:
	ruff check . --fix

format:
	ruff format .

type-check:
	mypy ai_audit_trail/ --ignore-missing-imports

quality: lint format type-check
	@echo "All quality checks passed."

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------
docker-up:
	docker compose up -d
	@echo "Services started. API at http://localhost:8000"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-rebuild:
	docker compose build --no-cache && docker compose up -d

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
clean:
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.db" -not -path "./.git/*" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	@echo "Cleaned."

verify-chain:
	@echo "Verifying audit chain integrity..."
	python -c "
from ai_audit_trail.chain import AuditChain
chain = AuditChain('audit_trail.db')
r = chain.verify_chain()
status = '✅ VALID' if r.is_valid else '❌ TAMPERED'
print(f'Chain: {status} | entries: {r.total_entries} | root: {r.merkle_root[:32]}...')
"
