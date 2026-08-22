"""FastAPI application entry point."""

from fastapi import FastAPI

from nlgcp_api.config import settings

app = FastAPI(title="NLGCP API", version="0.1.0")


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    """Return process liveness without asserting dependency health."""
    return {"status": "ok", "service": settings.service_name}
