# PMIND Veo MCP Server

> ⚠️ **Experimental**: This MCP server is in an experimental state and may have rough edges. Please report any issues you encounter.

A Python implementation of an MCP (Model Context Protocol) server using FastMCP that provides tools for generating videos with Google's Veo AI models through the Gemini API. This server uses a subprocess-based architecture for reliable long-running video generation tasks with the official google-genai Python SDK.

## 🎯 Features

### Core Capabilities

- **Video Generation**: Generate videos from text prompts using Veo models
- **Subprocess Architecture**: Non-blocking video generation with isolated subprocess handling
- **Progress Tracking**: Real-time status updates via state file monitoring
- **Video Downloads**: Download completed videos using the official google-genai SDK
- **Multiple Generations**: Track and manage multiple concurrent video generations
- **Process Management**: Graceful cancellation and cleanup of generation processes


## Installation & Setup

### Step 1: Clone the Repository

```bash
git clone https://github.com/yourusername/pmind-veo-mcp.git
cd pmind-veo-mcp
```

### Step 2: Install Dependencies

```bash
# Install dependencies using uv
uv sync
```

### Step 3: Set Up API Key

1. Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
2. Create a `.env` file in the project root:

```bash
cp .env.example .env
```

3. Edit `.env` and add your configuration:

```env
# Required: Your Gemini API key for Veo access
GEMINI_API_KEY=your_api_key_here

# Required: Default Veo model to use
# Options: veo-2.0-generate-001, veo-3.0-generate-preview
VEO_MODEL=veo-3.0-generate-preview

# Optional: Configuration directory (default: ~/.pmind-veo-mcp)
# CONFIG_DIR=/path/to/config
```

### Step 4: Configure with Your Client

Add the MCP server to your client's MCP configuration:

```json
{
  "mcpServers": {
    "pmind-veo": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/pmind-veo-mcp", "pmind-veo-mcp"]
    }
  }
}
```


## Configuration

### Required Environment Variables

- `GEMINI_API_KEY`: Your Gemini API key with video generation access
- `VEO_MODEL`: Default model (must be full API name):
  - `veo-2.0-generate-001` for Veo 2
  - `veo-3.0-generate-preview` for Veo 3

### Optional Environment Variables

- `CONFIG_DIR`: Directory for state files and downloads (default: `~/.pmind-veo-mcp`)

## Usage

Once configured, the server provides tools through your MCP client.




## MCP Tools Reference

- **`veo_generate_video`** - Start video generation with a text prompt
- **`veo_check_generation`** - Check the status of a video generation
- **`veo_download_video`** - Download a completed video
- **`veo_list_sessions`** - List all video generation sessions  
- **`veo_cleanup_sessions`** - Clean up old generation sessions


