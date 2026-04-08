"""
Application configuration.
Central authority settings; no auto-approval; strict state transitions.
"""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Central config for VISHWAAS Master."""

    # API
    app_name: str = "VISHWAAS Master"
    debug: bool = False

    # Database
    database_url: str = "sqlite:///./vishwaas_master.db"

    # VPN IP pool for approved nodes (10.10.10.0/24, .0 and .1 reserved)
    vpn_network: str = "10.10.10"
    vpn_start: int = 2
    vpn_end: int = 254

    # Agent call timeout (seconds)
    agent_timeout: float = 10.0

    # Deployment environment: "development" or "production"
    # In production mode, startup aborts if insecure defaults are detected.
    environment: str = "development"

    # Comma-separated allowed CORS origins.
    # Example: "https://dashboard.example.com,http://localhost:3000"
    allowed_origins: str = "http://localhost:3000,http://localhost:5173"

    # Token sent to node agents (X-VISHWAAS-TOKEN); must match agent's master_token
    agent_token: str = ""

    # Dashboard authentication (single-admin JWT)
    # Generate hash: python3 -c "from passlib.hash import bcrypt; print(bcrypt.hash('yourpassword'))"
    # Leave empty to disable auth (dev mode)
    admin_username: str = "admin"
    admin_password_hash: str = ""
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 480  # 8 hours

    class Config:
        env_file = ".env"
        env_prefix = "VISHWAAS_"


settings = Settings()
