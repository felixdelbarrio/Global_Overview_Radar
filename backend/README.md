Backend for Global Overview Radar

This package contains the backend services for Global Overview Radar. It powers
multi-source ingestion, sentiment enrichment, cache generation, and the API
consumed by the dashboard.

Quick start

1. Create a virtual environment and install dependencies:

    python -m venv .venv
    .venv/bin/python -m pip install -r requirements.txt

2. Install backend in editable mode:

    .venv/bin/python -m pip install -e backend

3. Run tests:

    .venv/bin/python -m pytest
