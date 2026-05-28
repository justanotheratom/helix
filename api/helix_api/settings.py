from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HELIX_", extra="ignore")

    baked_repo_sha: str = "unknown"
    database_url: str = "postgresql+psycopg://helix:helix-local-dev@helix-postgres:5432/helix"
    redis_url: str = "redis://helix-redis:6379/0"
    blob_endpoint: str = "http://helix-minio:9000"
    blob_access_key: str = "helix"
    blob_secret_key: str = "helix-local-dev-minio"
    blob_bucket: str = "helix"
    public_base_url: str = "http://127.0.0.1:7000"
    # Consumer config baked into the snapshot; supplies program/version
    # inference + langfuse project + ports. Generic defaults; real values
    # come from the consumer .helix.toml.
    config_path: str = "/repo-snapshot/.helix.toml"
    langfuse_public_origin: str = "http://127.0.0.1:3010"


class LangfuseSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    langfuse_internal_base_url: str = "http://langfuse-web:3000"
    langfuse_init_user_email: str = ""
    langfuse_init_user_password: str = ""
    langfuse_init_project_id: str = "helix"   # generic default; overridden by env/config
    # The project keys the worker uses to publish traces also let helix-api
    # READ traces via the Langfuse REST API (HTTP basic, public:secret).
    langfuse_init_project_public_key: str = ""
    langfuse_init_project_secret_key: str = ""


settings = Settings()
langfuse_settings = LangfuseSettings()


@lru_cache(maxsize=1)
def helix_config():
    """Load the consumer HelixConfig (best-effort). Returns None if absent so
    the API still boots before any snapshot is baked."""
    try:
        from helix_config import load_config
        return load_config(settings.config_path)
    except Exception:
        return None


def langfuse_project_id() -> str:
    cfg = helix_config()
    if cfg is not None:
        return cfg.stack.langfuse_project_id
    return langfuse_settings.langfuse_init_project_id
