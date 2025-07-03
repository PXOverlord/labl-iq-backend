from pydantic_settings import BaseSettings
from pathlib import Path
from typing import List

class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "Labl IQ Rate Analyzer"
    APP_VERSION: str = "1.0.0"
    
    # Database
    DATABASE_URL: str = "postgresql://username:password@localhost:5432/labl_iq_db?schema=public"
    
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
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create settings instance
settings = Settings()

# Ensure upload directory exists
settings.UPLOAD_DIR.mkdir(exist_ok=True)
