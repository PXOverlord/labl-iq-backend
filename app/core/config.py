from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List, Optional
import os

class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "Labl IQ Rate Analyzer"
    APP_VERSION: str = "1.0.0"
    
    # Database
    DATABASE_URL: Optional[str] = None
    
    # JWT Configuration
    SECRET_KEY: str = "your-super-secret-key-for-access-tokens"
    REFRESH_SECRET_KEY: str = "your-super-secret-key-for-refresh-tokens"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    
    # Application Settings
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"
    
    # File upload settings
    UPLOAD_DIR: Path = Path(__file__).parent.parent.parent / "uploads"
    ALLOWED_EXTENSIONS: List[str] = ["csv", "xlsx", "xls"]
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB
    
    # Amazon rate settings
    DEFAULT_AMAZON_RATE: float = 0.50  # Default rate per package
    DEFAULT_FUEL_SURCHARGE: float = 0.16  # 16% fuel surcharge
    
    # UI settings
    THEME_COLOR_PRIMARY: str = "#000000"  # Black
    THEME_COLOR_SECONDARY: str = "#FFFFFF"  # White
    THEME_COLOR_ACCENT: str = "#CCCCCC"  # Light gray
    
    # Performance settings
    ZONE_MATRIX_CACHE_ENABLED: bool = True
    ZONE_MATRIX_CACHE_TTL: int = 3600  # 1 hour
    API_RATE_LIMIT: int = 100  # requests per minute
    
    # AI assistant configuration
    AI_ASSISTANT_PROVIDER: str = "local"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    AI_ASSISTANT_SYSTEM_PROMPT: str = (
        "You are LABL IQ's shipping intelligence assistant. Help users analyze rates, uploads, settings, and insights."
    )
    AI_ASSISTANT_MAX_HISTORY: int = 20
    AI_ASSISTANT_DATA_DIR: Path = Path(__file__).resolve().parent.parent / "data" / "assistant_sessions"

    # Logging settings
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Set default DATABASE_URL if not provided
        if not self.DATABASE_URL:
            self.DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://username:password@localhost:5432/labl_iq_db?schema=public")
        
        # Ensure upload directory exists
        self.UPLOAD_DIR.mkdir(exist_ok=True)
        
        # Ensure assistant data directory exists
        self.AI_ASSISTANT_DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Validate critical settings
        self._validate_settings()
    
    def _validate_settings(self):
        """Validate critical settings"""
        if not self.SECRET_KEY or self.SECRET_KEY == "your-super-secret-key-for-access-tokens":
            raise ValueError("SECRET_KEY must be set to a secure value")
        
        if not self.REFRESH_SECRET_KEY or self.REFRESH_SECRET_KEY == "your-super-secret-key-for-refresh-tokens":
            raise ValueError("REFRESH_SECRET_KEY must be set to a secure value")

# Create settings instance
try:
    settings = Settings()
except Exception as e:
    print(f"Configuration error: {e}")
    # Fallback to basic settings for development
    settings = Settings(
        SECRET_KEY="dev-secret-key-change-in-production",
        REFRESH_SECRET_KEY="dev-refresh-secret-key-change-in-production"
    )
