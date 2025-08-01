"""Configuration handling for Veo MCP server"""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


class Config(BaseModel):
    """Server configuration"""

    config_dir: str = Field(description="Configuration directory path")
    gemini_api_key: str = Field(description="Gemini API key for Veo access")
    veo_model: Literal["veo-2.0-generate-001", "veo-3.0-generate-preview", "veo-3.0-fast-generate-preview"] = Field(
        description="Default Veo model to use"
    )

    @field_validator("config_dir")
    @classmethod
    def create_config_dir(cls, v: str) -> str:
        """Create config directory if it doesn't exist"""
        Path(v).mkdir(parents=True, exist_ok=True)
        return v

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        # Load .env file if it exists
        load_dotenv()

        # Get configuration directory with default
        config_dir = os.environ.get("CONFIG_DIR", str(Path.home() / ".pmind-veo-mcp"))

        # Create config with Pydantic validation
        return cls(
            config_dir=config_dir,
            gemini_api_key=os.environ.get("GEMINI_API_KEY"),
            veo_model=os.environ.get("VEO_MODEL"),
        )
