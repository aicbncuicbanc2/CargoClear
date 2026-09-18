from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    # Overridable because Google retires model ids on their own schedule:
    # gemini-2.0-flash was hardcoded here and started returning 404 with
    # "no longer available". Set GEMINI_MODEL in .env to move without a
    # code change.
    gemini_model: str = "gemini-3.6-flash"
    dataset_source: str = "data"


settings = Settings()
