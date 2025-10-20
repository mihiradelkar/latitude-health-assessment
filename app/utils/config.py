# app\services\mcp_manager.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    """Application settings"""
    
    # API Keys
    anthropic_api_key: str
    openai_api_key: str | None = None
    
    # Database
    database_url: str = "sqlite:///./latitude_health.db"
    
    # App Settings
    app_env: str = "development"
    debug: bool = True
    
    # LLM Settings
    default_model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 4000
    temperature: float = 0.1  # Changed from 0.3 - lower = more consistent
    
    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache
def get_settings():
    return Settings()

settings = get_settings()