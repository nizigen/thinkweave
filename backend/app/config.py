"""应用配置 — 从 .env 读取所有参数"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 数据库
    postgres_url: str = "postgresql+asyncpg://agent_user:agent_pass@localhost:5432/agent_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    default_model: str = "gpt-4o"

    # 应用
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
