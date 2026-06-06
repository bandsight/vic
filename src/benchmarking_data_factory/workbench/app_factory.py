from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def create_workbench_app(*, static_dir: Path) -> FastAPI:
    app = FastAPI(title="EBA Workbench")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    apps_dir = static_dir.parent / "apps"
    if apps_dir.exists():
        app.mount("/apps", StaticFiles(directory=apps_dir, html=True), name="apps")
    return app
