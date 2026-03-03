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

    # Token sent to node agents (X-VISHWAAS-TOKEN); must match agent's master_token
    agent_token: str = ""

    class Config:
        env_file = ".env"
        env_prefix = "VISHWAAS_"


settings = Settings()
