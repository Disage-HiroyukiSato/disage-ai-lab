from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):

    llm_url: str

    api_timeout: int = 600

    log_level: str = "INFO"

    model_config = SettingsConfigDict(

        env_file="/app/config/rag.env",

        extra="ignore"

    )

settings = Settings()