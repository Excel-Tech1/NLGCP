"""FastAPI application entry point."""

from fastapi import FastAPI

from nlgcp_api.config import settings
from nlgcp_api.v1_router import v1_router

app = FastAPI(title="NLGCP API", version="0.1.0")
app.include_router(v1_router)


@app.get("/health", tags=["operations"])
def health() -> dict[str, str]:
    """Return process liveness without asserting dependency health."""
    return {"status": "ok", "service": settings.service_name}
