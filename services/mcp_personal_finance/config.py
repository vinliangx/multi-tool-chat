from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    chat_app_url: str = (
        "postgresql://chat_app_user:chat_app_passw0rd@localhost:5432/chat_app"
    )


settings = Settings()
