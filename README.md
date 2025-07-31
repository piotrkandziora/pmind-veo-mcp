# PMIND Veo MCP Server

A Python implementation of an MCP (Model Context Protocol) server using FastMCP that provides tools for generating videos with Google's Veo AI models through the Gemini API. This server uses a subprocess-based architecture for reliable long-running video generation tasks with the official google-genai Python SDK.

## 🎯 Features

### Core Capabilities

- **Video Generation**: Generate videos from text prompts using Veo models
- **Subprocess Architecture**: Non-blocking video generation with isolated subprocess handling
- **Progress Tracking**: Real-time status updates via state file monitoring
- **Video Downloads**: Download completed videos using the official google-genai SDK
- **Multiple Generations**: Track and manage multiple concurrent video generations
- **Process Management**: Graceful cancellation and cleanup of generation processes

### Key Features

- **Secure API Key Handling**: API keys passed via environment variables, never in command arguments
- **Atomic State Updates**: Reliable state persistence using atomic file operations
- **Process Isolation**: Each generation runs in an isolated subprocess
- **Session Management**: Clean up old generation sessions
- **Comprehensive Logging**: Consistent logging throughout the application
- **Type Safety**: Full type annotations with Pydantic validation

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

### `veo_generate_video`
Starts video generation in a background subprocess.

**Parameters:**
- `prompt` (str, required): Text description of the video to generate
- `model` (str): Model to use - "veo-2.0-generate-001" or "veo-3.0-generate-preview" (defaults to VEO_MODEL)
- `aspect_ratio` (str): "16:9" or "9:16" (default: "16:9")
- `negative_prompt` (str): Elements to avoid in the video
- `person_generation` (str): "dont_allow" or "allow_adult" (default: "allow_adult")
- `resolution` (str): "720p" or "1080p" (if supported by model)
- `number_of_videos` (int): Number of variations 1-4 (default: 1)
- `duration_seconds` (int): Video duration in seconds (optional, SDK will use model default if not specified)
- `seed` (int): Random seed for reproducibility
- `enhance_prompt` (bool): Auto-enhance the prompt (default: false)
- `generate_audio` (bool): Generate audio for the video (default: false)
- `output_gcs_uri` (str): GCS bucket where to save generated videos
- `fps` (int): Frames per second for video generation

**Returns:**
```json
{
  "success": true,
  "session_id": "gen_abc123_1234567890",
  "status": "starting",
  "pid": 12345,
  "message": "Video generation started. Use veo_check_generation with session_id 'gen_abc123_1234567890' to monitor progress.",
  "model": "veo-3.0-generate-preview",
  "parameters": {
    "prompt": "Your prompt here",
    "aspect_ratio": "16:9",
    "duration_seconds": null,
    "number_of_videos": 1
  }
}
```

### `veo_check_generation`
Checks the status of a video generation subprocess.

**Parameters:**
- `session_id` (str, required): Session ID from veo_generate_video

**Returns:**
```json
{
  "session_id": "gen_abc123_1234567890",
  "status": "completed",  // or "running", "failed", "cancelled"
  "progress": "generation completed",
  "videos": [
    {"uri": "files/...", "mime_type": "video/mp4"}
  ],
  "video_count": 1,
  "completed_at": "2024-01-01T12:00:00Z"
}
```

### `veo_list_sessions` (alias: `veo_list_generations`)
Lists all video generation sessions.

**Parameters:**
- `active_only` (bool): Only show active generations (default: false)

**Returns:**
```json
{
  "generations": [
    {
      "session_id": "gen_abc123_1234567890",
      "status": "completed",
      "prompt": "A serene sunset...",
      "model": "veo-3",
      "started_at": "2024-01-01T11:00:00Z",
      "video_count": 1
    }
  ],
  "total": 1
}
```

### `veo_cleanup_sessions`
Clean up old generation sessions and their files.

**Parameters:**
- `older_than_days` (int): Delete sessions older than this many days (default: 7, minimum: 1)
- `completed_only` (bool): Only cleanup completed/failed sessions (default: true)

**Returns:**
```json
{
  "success": true,
  "cleaned_sessions": 5,
  "message": "Cleaned up 5 old sessions"
}
```

### `veo_download_video`
Downloads a generated video from a completed generation session.

**Parameters:**
- `session_id` (str, required): Session ID from veo_generate_video
- `video_index` (int): Index of video to download for multiple samples, 0-based (default: 0)
- `output_dir` (str): Directory to save the video (optional, defaults to downloads directory)

**Returns:**
```json
{
  "file_path": "/path/to/veo_gen_abc123_0_20240101_120000.mp4",
  "file_size": 5242880,
  "success": true,
  "message": "Video downloaded successfully to /path/to/veo_gen_abc123_0_20240101_120000.mp4"
}
```

## Architecture

### SDK-Only Implementation
This server uses only the official google-genai Python SDK for all operations:
- Video generation via `client.models.generate_videos()`
- Operation polling via `client.operations.get()`
- Video download via `client.files.download()`
- No direct REST API calls or custom HTTP requests

### Subprocess Architecture
- Each video generation runs in an isolated subprocess
- Main server remains responsive during long generation times
- State persistence via atomic file operations
- Graceful process termination and cleanup

## Important Notes

### Video Storage
- Generated videos are stored on Google's servers temporarily
- Always download videos you want to keep permanently
- Downloaded videos are saved to `CONFIG_DIR/downloads/session_id/` by default


### Limitations

- Veo video generation requires API allowlist access from Google
- All videos include SynthID watermarking for AI content identification  
- Generation time varies depending on video parameters
- API quotas and rate limits apply based on your Gemini API key
- Person generation may be restricted based on your region
- Some parameters may not be supported by all models

## Troubleshooting

### Common Issues

1. **API Key Errors**
   - Ensure `GEMINI_API_KEY` is set in your `.env` file
   - Verify the key has video generation permissions
   - Check API quotas in Google AI Studio

2. **Model Not Found**
   - Use full model names: `veo-2.0-generate-001` or `veo-3.0-generate-preview`
   - Check `VEO_MODEL` in your `.env` file

3. **Parameter Type Errors**
   - The server automatically handles string-to-type conversions for MCP clients
   - Parameters like `number_of_videos`, `duration_seconds`, and booleans can be passed as strings


4. **Subprocess Issues**
   - Check if the worker process is running: Look for `pid` in status
   - Review logs for subprocess errors
   - Ensure proper Python path and dependencies

5. **Download Failures**
   - Videos expire after 2 days
   - Ensure the generation completed successfully
   - Check file permissions in the output directory

### Debugging

1. **Enable Debug Logging**
   ```python
   # Set logging level in your application
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Check State Files**
   ```bash
   # State files are in CONFIG_DIR/generation_states/
   ls ~/.pmind-veo-mcp/generation_states/
   cat ~/.pmind-veo-mcp/generation_states/gen_*.json
   ```

3. **Monitor Subprocess Output**
   - Worker logs are written to stderr
   - Check for Python tracebacks or API errors

