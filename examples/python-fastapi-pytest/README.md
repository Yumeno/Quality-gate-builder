# demo-api (python-fastapi-pytest example)

Minimal FastAPI application used as a qgb example pack.

## Usage

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
uvicorn demo_api.main:app --reload
```

## Running the quality gate

```powershell
python -m qgb run REQ-APP-001 --path . --yes
```
