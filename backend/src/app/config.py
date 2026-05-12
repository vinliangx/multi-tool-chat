from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_provider: Literal["anthropic", "ollama"] = "anthropic"

    anthropic_api_key: str = ""
    model_name: str = "claude-sonnet-4-6"
    summarizer_model: str = "claude-haiku-4-5-20251001"
    embedding_model: str = "embeddinggemma:latest"
    vision_model: str = "claude-sonnet-4-6"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_summarizer_model: str = "qwen2.5:7b"
    ollama_embedding_model: str = "embeddinggemma"
    ollama_vision_model: str = "qwen3-vl:latest"

    aws_region: str = "us-east-1"
    sessions_table: str = "chat-sessions"
    tool_results_table: str = "chat-tool-results"
    tool_results_bucket: str = "chat-tool-results-local"

    tool_result_inline_token_limit: int = 4000
    tool_result_summarize_token_limit: int = 8000
    context_window_token_limit: int = 16000

    cors_origins: list[str] = ["http://localhost:5173"]
    redis_url: str = "redis://localhost:6379"
    memory_api_url: str = "http://localhost:8000"

    external_s3_endpoint_url: str = "http://localhost:9444"
    internal_s3_endpoint_url: str = "http://localhost:9444"
    aws_access_key_id: str = "ACCESS_KEY_ID"
    aws_secret_access_key: str = "ACCESS_KEY"
    region_name: str = "us-east-1"
    bucket_name: str = "file-uploads"


settings = Settings()
