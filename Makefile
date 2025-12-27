.PHONY: help setup db server demo clean install test docker-up docker-down docker-logs ui

UV := uv
PYTHON := uv run python
DB_NAME := contextgraph
DB_URL := postgresql://localhost/$(DB_NAME)

help:
	@echo "contextgraph - Decision traces as data"
	@echo ""
	@echo "Exception Desk Demo:"
	@echo "  make demo            - Run full Exception Desk demo (both tickets)"
	@echo "  make demo-ticket     - Process single ticket: make demo-ticket T=SUP-4312"
	@echo "  make ui              - Open the Decision Explorer UI"
	@echo ""
	@echo "Docker (recommended):"
	@echo "  make docker-up       - Start server + postgres via docker-compose"
	@echo "  make docker-down     - Stop containers"
	@echo "  make docker-logs     - Tail server logs"
	@echo ""
	@echo "Local development:"
	@echo "  make setup           - Create database and install dependencies"
	@echo "  make server          - Start the API server (requires local postgres)"
	@echo "  make install         - Install Python package locally (uses uv)"
	@echo "  make test            - Run tests"
	@echo "  make clean           - Remove generated files"
	@echo ""

# Exception Desk Demo
demo:
	@$(PYTHON) demo/cli.py demo

demo-ticket:
	@test -n "$(T)" || (echo "Usage: make demo-ticket T=SUP-4312" && exit 1)
	@$(PYTHON) demo/cli.py run $(T) --explain

ui:
	@echo "Opening Decision Explorer UI..."
	@open ui/index.html 2>/dev/null || xdg-open ui/index.html 2>/dev/null || echo "Open ui/index.html in your browser"

# Docker commands
docker-up:
	docker-compose up -d --build
	@echo "Waiting for services..."
	@sleep 3
	@curl -s http://localhost:8080/health | python3 -m json.tool || echo "Server starting..."
	@echo "Server running at http://localhost:8080"

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f server

docker-clean:
	docker-compose down -v --rmi local

# Local development
setup: db install
	@echo "Setup complete. Run 'make server' to start."

db:
	@echo "Creating database..."
	-createdb $(DB_NAME) 2>/dev/null || true
	psql $(DB_NAME) < storage/postgres/schema.sql
	@echo "Database ready."

server:
	DATABASE_URL=$(DB_URL) $(UV) run uvicorn server.main:app --reload --port 8080

install:
	$(UV) pip install -e sdk/python[all]

sync:
	cd sdk/python && $(UV) sync

test:
	$(UV) run pytest sdk/python/tests -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf sdk/python/*.egg-info 2>/dev/null || true
	rm -rf .venv 2>/dev/null || true

# Dev shortcuts
.PHONY: curl-health curl-explain curl-list

curl-health:
	curl -s http://localhost:8080/health | python3 -m json.tool

curl-list:
	curl -s http://localhost:8080/v1/decisions | python3 -m json.tool

curl-explain:
	@test -n "$(ID)" || (echo "Usage: make curl-explain ID=dec_xxx" && exit 1)
	curl -s http://localhost:8080/v1/decisions/$(ID)/explain | python3 -m json.tool
