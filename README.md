# BBVA BugResolutionRadar (starter)

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]" || pip install -e .
cp .env.example .env