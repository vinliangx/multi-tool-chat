from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    finance_db_url: str = (
        "postgresql://finance_user:finance_password@localhost:5432/finance_db"
    )


settings = Settings()
