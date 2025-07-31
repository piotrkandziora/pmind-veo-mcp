"""Shared logging configuration for Veo MCP server"""

import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO", format: Optional[str] = None) -> None:
    """
    Configure logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Custom log format string
    """
    if format is None:
        format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format,
        handlers=[logging.StreamHandler(sys.stderr)],
    )
