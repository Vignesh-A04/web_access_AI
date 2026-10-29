"""Application configuration using Pydantic Settings."""

import os
from typing import List, Set
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Gemini LLM Settings
    gemini_api_key: str = Field(default="", description="Google Gemini API Key")
    gemini_model: str = Field(default="gemini-3.5-flash-lite", description="Supported Gemini model name")

    @property
    def GEMINI_MODEL(self) -> str:
        """Uppercase alias for single source of truth model configuration."""
        return self.gemini_model


    # Backend Server
    backend_host: str = Field(default="127.0.0.1", description="Backend host to bind to")
    backend_port: int = Field(default=8000, description="Backend port to bind to")
    frontend_origin: str = Field(default="http://localhost:5173", description="Frontend origin for CORS")

    # Browser Automation Settings
    browser_headless: bool = Field(default=True, description="Whether to run browser in headless mode")
    max_agent_steps: int = Field(default=15, description="Maximum agent tool steps per task")
    task_timeout_seconds: int = Field(default=180, description="Maximum execution time for a task")
    navigation_timeout_ms: int = Field(default=20000, description="Timeout for page navigation in ms")
    action_timeout_ms: int = Field(default=10000, description="Timeout for browser actions in ms")

    # WhatsApp Web & CDP Settings
    chrome_cdp_url: str = Field(
        default="http://127.0.0.1:9222",
        description="CDP endpoint URL for connecting to dedicated Chrome session"
    )
    whatsapp_timeout_seconds: int = Field(
        default=45,
        description="Timeout for WhatsApp Web navigation and element resolution"
    )


    # Security & SSRF Protection
    allow_local_test_domains: bool = Field(
        default=False,
        description="Whether localhost / 127.0.0.1 on designated test ports is permitted for local integration testing"
    )
    trusted_domains_allowlist: str = Field(
        default="example.com,httpbin.org",
        description="Comma-separated list of explicitly trusted external domains"
    )

    # Logging and Artifacts
    log_level: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)")
    screenshot_dir: str = Field(default="task_artifacts/screenshots", description="Directory to store task screenshots")

    def get_trusted_domains(self) -> Set[str]:
        """Return the set of explicitly trusted domains."""
        if not self.trusted_domains_allowlist:
            return set()
        return {d.strip().lower() for d in self.trusted_domains_allowlist.split(",") if d.strip()}

    def is_domain_trusted(self, domain: str) -> bool:
        """Check if a domain or its parent domain is in the trusted allowlist."""
        domain = domain.lower().strip()
        trusted = self.get_trusted_domains()
        if domain in trusted:
            return True
        # Check subdomains, e.g. sub.example.com when example.com is in allowlist
        for t in trusted:
            if domain.endswith("." + t):
                return True
        return False

    def __repr__(self) -> str:
        """Safe representation without exposing secrets."""
        return (
            f"Settings(gemini_model='{self.gemini_model}', "
            f"backend='{self.backend_host}:{self.backend_port}', "
            f"headless={self.browser_headless}, "
            f"allow_local_test_domains={self.allow_local_test_domains}, "
            f"gemini_api_key={'***SET***' if self.gemini_api_key else '***NOT SET***'})"
        )


settings = Settings()
