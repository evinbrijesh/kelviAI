.PHONY: dev install test lint simulate rehearse clean db-up db-down db-logs

SCENARIO ?= appointment_malayalam
SCENARIO_MODULE = $(subst -,_,$(SCENARIO))
HOST ?= 0.0.0.0
PORT ?= 8000

ifeq ($(OS),Windows_NT)
VENV_PYTHON := .venv/Scripts/python.exe
else
VENV_PYTHON := .venv/bin/python
endif
PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),python)

dev: db-up
	$(PYTHON) -m uvicorn app.main:app --reload --host $(HOST) --port $(PORT)

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m mypy app/

simulate:
	$(PYTHON) -m app.scenarios.$(SCENARIO_MODULE)

rehearse:
	$(PYTHON) -m app.scenarios.rehearsal

db-up:
	docker compose up -d --wait db

db-down:
	docker compose down

db-logs:
	docker compose logs -f db

clean:
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
