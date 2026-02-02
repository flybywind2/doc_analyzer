"""
Application Configuration
"""
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    app_name: str = "AI Application Evaluator"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Confluence
    confluence_base_url: str  # API 동기화용 URL (mirror 서버)
    confluence_link_base_url: Optional[str] = None  # 사용자 링크용 URL (실제 서버, 없으면 base_url 사용)
    confluence_username: str
    confluence_password: str
    confluence_space_key: str
    confluence_parent_page_id: str
    
    # LLM API (Primary)
    llm_api_base_url: str
    llm_api_key: str
    llm_credential_key: str
    llm_model_name: str = "gpt-oss"
    llm_system_name: str = "AI_Evaluation_System"
    llm_user_id: str = "system_user"

    # LLM API (Secondary - Optional for ensemble evaluation)
    llm_b_api_base_url: Optional[str] = None
    llm_b_api_key: Optional[str] = None
    llm_b_credential_key: Optional[str] = None
    llm_b_model_name: Optional[str] = None
    
    # Authentication
    secret_key: str
    access_token_expire_minutes: int = 60
    algorithm: str = "HS256"
    
    # Database
    database_url: str = "sqlite:///./data/app.db"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


settings = get_settings()
