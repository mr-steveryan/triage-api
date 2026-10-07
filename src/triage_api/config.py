from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    llm_stub: bool
    llm_prompt_version: str = Field(pattern=r"^v\d+$")

settings = Settings()
