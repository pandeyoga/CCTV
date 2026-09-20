"""Supervisor/uvicorn entry point: `uvicorn server:app`. Application lives in app/."""
from app.main import create_app

app = create_app()
