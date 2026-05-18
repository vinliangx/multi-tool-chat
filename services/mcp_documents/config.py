from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rag_db_url: str = (
        "postgresql://finance_user:finance_password@localhost:5432/finance_db"
    )
    redis_url: str = "redis://localhost:6379"

    internal_s3_endpoint_url: str = "http://localhost:9444"
    external_s3_endpoint_url: str = "http://localhost:9444"
    aws_access_key_id: str = "ACCESS_KEY_ID"
    aws_secret_access_key: str = "ACCESS_KEY"
    region_name: str = "us-east-1"
    bucket_name: str = "file-uploads"

    vision_model: str = "claude-sonnet-4-6"
    vision_provider: str = "anthropic"
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    embedding_model: str = "embeddinggemma:latest"
    embedding_dimensions: int = 768

    chunk_size: int = 1000
    chunk_overlap: int = 200


settings = Settings()
