"""Environment-backed API configuration."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REQUIRED_DATA_ROOT_DIRECTORIES = (
    "00-deliveries",
    "raw",
    "metadata",
    "external-products",
    "manifests",
    "quarantine",
    "working",
    "processed",
    "validation",
)


class Settings(BaseSettings):
    """Non-secret service settings."""

    model_config = SettingsConfigDict(
        env_prefix="NLGCP_",
        env_file=".env",
        extra="ignore",
    )

    service_name: str = "nlgcp-api"
    data_root: Path | None = None


def resolve_data_root(settings: Settings) -> Path:
    """Return the validated external scientific data root.

    Scientific workflows fail closed when the data root is not configured,
    does not exist, is not a directory, or lacks the required Phase 2
    vault structure.
    """

    if settings.data_root is None:
        raise RuntimeError(
            "NLGCP_DATA_ROOT is required for scientific data operations"
        )

    root = settings.data_root.expanduser().resolve()

    if not root.exists():
        raise RuntimeError(
            f"NLGCP_DATA_ROOT does not exist: {root}"
        )

    if not root.is_dir():
        raise RuntimeError(
            f"NLGCP_DATA_ROOT is not a directory: {root}"
        )

    missing = [
        name
        for name in REQUIRED_DATA_ROOT_DIRECTORIES
        if not (root / name).is_dir()
    ]

    if missing:
        raise RuntimeError(
            "NLGCP_DATA_ROOT is missing required directories: "
            + ", ".join(missing)
        )

    return root


settings = Settings()
