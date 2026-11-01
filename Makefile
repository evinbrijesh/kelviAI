.PHONY: dev install test lint simulate clean

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

install:
	pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .
	mypy app/

simulate:
	python app/scenarios/$(SCENARIO).py || echo "Scenario not yet implemented"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
