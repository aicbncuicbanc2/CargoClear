from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    dataset_source: str = "data"


settings = Settings()
