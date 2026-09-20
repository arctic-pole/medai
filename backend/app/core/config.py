from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read only from environment variables (.env in dev).

    Per medai_spec.yaml security.minimum_requirements: secrets_outside_source_code,
    environment_variables_for_credentials. Never hard-code credentials here.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://medai:medai@localhost:5432/medai"

    jwt_secret_key: str = "change-me-in-real-environments"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7


settings = Settings()
