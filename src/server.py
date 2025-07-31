"""Main MCP server implementation using FastMCP"""

import asyncio
import logging

from fastmcp import FastMCP

from .config import Config
from .services import video_generation
from .utils.logging import setup_logging

# Configure logging
setup_logging(level="INFO", format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def create_server() -> FastMCP:
    """Create and configure the MCP server"""
    # Load configuration
    logger.debug("Loading configuration from environment...")
    try:
        config = Config.from_env()
        logger.debug("Configuration loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load configuration: {type(e).__name__}: {str(e)}")
        raise

    # Initialize FastMCP server
    mcp = FastMCP(
        name="PMIND Veo3 JSON MCP Server",
        instructions="""
This server provides Google Veo video generation capabilities through MCP tools.

Available tools:

Video Generation:
- veo_generate_video: Generate videos from text or image prompts
- veo_check_operation: Check generation operation status
- veo_list_operations: List all generation operations
- veo_download_video: Download completed videos

Features:
- Direct Google Gemini API integration
- Support for both Veo 2 (veo-2.0-generate-001) and Veo 3 (veo-3.0-generate-preview) models
- Text-to-video and image-to-video generation
- Multiple aspect ratios and resolutions
- Optional wait for completion
- SynthID watermarking for AI content identification

Note: Videos are stored on Google's servers for 2 days. Download within this period to save permanently.
""",
    )

    # Register services
    logger.debug("Registering MCP services...")

    # Register video generation tools
    video_generation.register_tools(mcp, config)
    logger.debug("Video generation tools registered")

    logger.info("MCP server initialized successfully")
    return mcp


# Create the server instance
mcp = create_server()


def main():
    """Main entry point for the server"""

    # Run the server
    logger.info("Starting PMIND Veo3 JSON MCP server...")
    asyncio.run(mcp.run())


if __name__ == "__main__":
    main()
