.PHONY: help install dev-install test lint format clean docker-up docker-down docker-logs docker-rebuild docker-status docker-check migrate api-start api-dev api-test mcp-start mcp-dev ui-install ui-dev ui-build ui-test

help:
	@echo "Available commands:"
	@echo ""
	@echo "Backend:"
	@echo "  make install       - Install production dependencies"
	@echo "  make dev-install   - Install development dependencies"
	@echo "  make test          - Run tests with coverage"
	@echo "  make lint          - Run linters"
	@echo "  make format        - Format code"
	@echo "  make migrate       - Run database migrations"
	@echo "  make api-start     - Start API server (production)"
	@echo "  make api-dev       - Start API server (development with reload)"
	@echo "  make api-test      - Test API endpoints"
	@echo "  make mcp-start     - Start MCP server (stdio transport)"
	@echo "  make mcp-dev       - Start MCP server (development mode)"
	@echo ""
	@echo "Frontend (UI):"
	@echo "  make ui-install    - Install UI dependencies"
	@echo "  make ui-dev        - Start UI development server"
	@echo "  make ui-build      - Build UI for production"
	@echo "  make ui-test       - Run UI tests"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-up     - Start all Docker services (including UI)"
	@echo "  make docker-down   - Stop all Docker services"
	@echo "  make docker-logs   - View logs from all services"
	@echo "  make docker-check  - Check health of all services"
	@echo "  make docker-status - Show status of all containers"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         - Clean cache and build files"

install:
	pip install -r requirements.txt

dev-install:
	pip install -r requirements.txt -r requirements-dev.txt
	pre-commit install

test:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term

lint:
	flake8 src/ tests/
	mypy src/
	pylint src/
	bandit -r src/

format:
	black src/ tests/
	isort src/ tests/

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .coverage htmlcov dist build

docker-up:
	docker-compose -f docker/docker-compose.yml up -d

docker-down:
	docker-compose -f docker/docker-compose.yml down

migrate:
	alembic upgrade head

# API commands
api-start:
	uvicorn src.api.main:app --host 0.0.0.0 --port 8080 --workers 4

api-dev:
	uvicorn src.api.main:app --host 0.0.0.0 --port 8080 --reload

api-test:
	python scripts/test_api.py

# MCP commands
mcp-start:
	python -m src.mcp_server

mcp-dev:
	python src/mcp_server/main.py

# UI commands
ui-install:
	cd ui && npm install

ui-dev:
	cd ui && npm run dev

ui-build:
	cd ui && npm run build

ui-test:
	cd ui && npm test

# Docker commands
docker-logs:
	docker-compose -f docker/docker-compose.yml logs -f

docker-rebuild:
	docker-compose -f docker/docker-compose.yml up -d --build

docker-status:
	docker-compose -f docker/docker-compose.yml ps

docker-check:
	@echo "Checking services health..."
	@powershell -ExecutionPolicy Bypass -File scripts/check-services.ps1

