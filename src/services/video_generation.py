"""Video generation MCP tools using subprocess-based approach"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, Literal, Optional, Union

from fastmcp import FastMCP
from pydantic import Field

from ..config import Config
from ..utils.common import parse_bool_param, parse_int_param
from ..utils.generation_manager import GenerationManager
from ..utils.veo_client import VeoClient

logger = logging.getLogger(__name__)


def register_tools(mcp: FastMCP, config: Config):
    """Register video generation tools with subprocess-based approach"""

    # Initialize generation manager with state directory
    generation_manager = GenerationManager(state_dir=str(Path(config.config_dir) / "generation_states"))

    @mcp.tool
    async def veo_generate_video(
        prompt: Annotated[
            str,
            Field(
                description="Text prompt describing the video to generate. Be specific about visual elements, style, and movement.",
            ),
        ],
        # Model selection
        model: Annotated[
            Optional[Literal["veo-2.0-generate-001", "veo-3.0-generate-preview"]],
            Field(
                default="veo-3.0-generate-preview",
                description="Veo model to use for generation",
            ),
        ] = "veo-3.0-generate-preview",
        # Video parameters
        aspect_ratio: Annotated[
            Literal["16:9", "9:16"],
            Field(
                default="16:9",
                description="Video aspect ratio (SDK supports 16:9 and 9:16)",
            ),
        ] = "16:9",
        negative_prompt: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Elements to avoid in the generation (e.g., 'low quality, blurry')",
            ),
        ] = None,
        person_generation: Annotated[
            Literal["dont_allow", "allow_adult"],
            Field(
                default="allow_adult",
                description="Control person generation in videos (SDK supports dont_allow, allow_adult)",
            ),
        ] = "allow_adult",
        resolution: Annotated[
            Optional[Literal["720p", "1080p"]],
            Field(default=None, description="Video resolution (if supported by model)"),
        ] = None,
        number_of_videos: Annotated[
            Union[int, str],
            Field(
                default=1,
                description="Number of video variations to generate (1-4)",
            ),
        ] = 1,
        duration_seconds: Annotated[
            Optional[Union[int, str]],
            Field(
                default=None,
                description="Video duration in seconds (2-15, optional, SDK will use model default if not specified)",
            ),
        ] = None,
        seed: Annotated[
            Optional[Union[int, str]],
            Field(default=None, description="Seed for reproducible generation"),
        ] = None,
        # Advanced options
        enhance_prompt: Annotated[
            Union[bool, str],
            Field(
                default=False,
                description="Let the model enhance your prompt for better results",
            ),
        ] = False,
        generate_audio: Annotated[
            Union[bool, str],
            Field(
                default=False,
                description="Generate audio for the video",
            ),
        ] = False,
        output_gcs_uri: Annotated[
            Optional[str],
            Field(
                default=None,
                description="GCS bucket where to save the generated videos",
            ),
        ] = None,
        fps: Annotated[
            Optional[Union[int, str]],
            Field(
                default=None,
                description="Frames per second for video generation",
            ),
        ] = None,
    ) -> Dict[str, Any]:
        """
        Generate videos using Google's Veo text-to-video models.

        This tool starts a background video generation process that:
        1. Initiates video generation with the specified parameters
        2. Monitors progress in the background

        To download generated videos, use veo_download_video after generation completes.

        Returns:
        - session_id: Use with veo_check_generation to monitor progress
        - status: Current generation status
        - pid: Process ID of the background worker

        Example:
            Generate a nature video: "Serene waterfall in a lush forest, cinematic lighting"
            Generate with specific style: "Cyberpunk cityscape at night, neon lights, rain"
        """
        try:
            # Parse parameters that might come as strings
            number_of_videos = parse_int_param(number_of_videos, default=1)
            duration_seconds = parse_int_param(duration_seconds)
            seed = parse_int_param(seed)
            fps = parse_int_param(fps)
            enhance_prompt = parse_bool_param(enhance_prompt) if enhance_prompt is not None else False
            generate_audio = parse_bool_param(generate_audio) if generate_audio is not None else False

            # Start generation process (no automatic download)
            result = generation_manager.start_generation(
                prompt=prompt,
                model=model,
                aspect_ratio=aspect_ratio,
                negative_prompt=negative_prompt,
                person_generation=person_generation,
                resolution=resolution,
                number_of_videos=number_of_videos,
                duration_seconds=duration_seconds,
                seed=seed,
                enhance_prompt=enhance_prompt,
                generate_audio=generate_audio,
                output_gcs_uri=output_gcs_uri,
                fps=fps,
                download_path=None,  # No automatic download
            )

            # Get initial status
            status = generation_manager.get_status(result["session_id"])

            return {
                "session_id": result["session_id"],
                "status": status.get("status", "starting"),
                "pid": result["pid"],
                "message": f"Video generation started. Use veo_check_generation with session_id '{result['session_id']}' to monitor progress.",
                "model": model,
                "parameters": {
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "duration_seconds": duration_seconds,
                    "number_of_videos": number_of_videos,
                },
            }

        except Exception as e:
            return {
                "error": f"Failed to start video generation: {str(e)}",
                "success": False,
            }

    @mcp.tool
    async def veo_check_generation(
        session_id: Annotated[str, Field(description="Session ID returned from veo_generate_video")],
    ) -> Dict[str, Any]:
        """
        Check the status of a video generation subprocess.

        This monitors the subprocess that is handling the video generation,
        not the Gemini API directly. The subprocess handles all API polling.

        If the generation has an operation_id, you can also use veo_check_operation
        to directly query Google's API for the operation status.
        """
        try:
            result = await asyncio.to_thread(generation_manager.get_status, session_id)

            if "error" in result and result["error"] == "Generation session not found":
                return {
                    "error": f"Session {session_id} not found",
                    "hint": "Use veo_list_generations to see active sessions",
                }

            # Return the result directly - it already has all the necessary fields
            return result

        except Exception as e:
            return {"error": f"Failed to check generation status: {str(e)}"}

    @mcp.tool
    async def veo_list_generations(
        active_only: Annotated[
            bool,
            Field(default=False, description="Only show active (running) generations"),
        ] = False,
    ) -> Dict[str, Any]:
        """
        List all video generation sessions.

        Shows all subprocess-based generation sessions with their current status.
        """
        try:
            result = await asyncio.to_thread(generation_manager.list_generations, active_only=active_only)

            # Format for display
            generations = []
            for gen in result:
                gen_info = {
                    "session_id": gen["session_id"],
                    "status": gen["status"],
                    "progress": gen.get("progress", ""),
                    "prompt": (gen["prompt"][:100] + "..." if len(gen["prompt"]) > 100 else gen["prompt"]),
                    "model": gen["model"],
                    "started_at": gen["started_at"],
                    "pid": gen.get("pid"),
                }

                # Add video count if completed
                if gen["status"] == "completed":
                    gen_info["video_count"] = len(gen.get("videos", []))

                # Add error if failed
                if gen.get("error"):
                    gen_info["error"] = gen["error"][:100] + "..." if len(gen["error"]) > 100 else gen["error"]

                generations.append(gen_info)

            return {
                "generations": generations,
                "total": len(generations),
                "active_only": active_only,
            }

        except Exception as e:
            return {"error": f"Failed to list generations: {str(e)}"}

    @mcp.tool
    async def veo_list_sessions(
        active_only: Annotated[
            bool,
            Field(default=False, description="Only show active (running) generations"),
        ] = False,
    ) -> Dict[str, Any]:
        """
        List all video generation sessions.

        Shows all subprocess-based generation sessions with their current status.
        """
        try:
            result = await asyncio.to_thread(generation_manager.list_generations, active_only=active_only)

            # Format for display
            sessions = []
            for gen in result:
                session_info = {
                    "session_id": gen["session_id"],
                    "status": gen["status"],
                    "progress": gen.get("progress", ""),
                    "prompt": (gen["prompt"][:100] + "..." if len(gen["prompt"]) > 100 else gen["prompt"]),
                    "model": gen["model"],
                    "started_at": gen["started_at"],
                    "pid": gen.get("pid"),
                }

                # Add video count if completed
                if gen["status"] == "completed":
                    session_info["video_count"] = len(gen.get("videos", []))

                # Add error if failed
                if gen.get("error"):
                    session_info["error"] = gen["error"][:100] + "..." if len(gen["error"]) > 100 else gen["error"]

                sessions.append(session_info)

            return {
                "sessions": sessions,
                "total": len(sessions),
                "active_only": active_only,
            }

        except Exception as e:
            return {"error": f"Failed to list sessions: {str(e)}"}

    @mcp.tool
    async def veo_cleanup_sessions(
        older_than_days: Annotated[
            Union[int, str],
            Field(
                default=7,
                description="Delete sessions older than this many days (minimum 1)",
            ),
        ] = 7,
        completed_only: Annotated[
            Union[bool, str],
            Field(
                default=True,
                description="Only cleanup completed/failed sessions",
            ),
        ] = True,
    ) -> Dict[str, Any]:
        """
        Clean up old generation sessions and their files.

        Removes state files and optionally downloaded videos for old sessions.
        """
        try:
            # Parse parameters that might come as strings
            older_than_days = parse_int_param(older_than_days, default=7)
            completed_only = parse_bool_param(completed_only) if completed_only is not None else True

            cleaned_count = 0
            cutoff_time = datetime.now().timestamp() - (older_than_days * 24 * 60 * 60)

            sessions = await asyncio.to_thread(generation_manager.list_generations)

            for session in sessions:
                # Parse session timestamp from ID
                try:
                    session_timestamp = int(session["session_id"].split("_")[-1])
                    if session_timestamp > cutoff_time:
                        continue  # Too recent
                except (ValueError, IndexError):
                    continue

                # Check if should cleanup
                if completed_only and session["status"] not in [
                    "completed",
                    "failed",
                    "cancelled",
                ]:
                    continue

                # Remove state file
                state_file = generation_manager._get_state_file(session["session_id"])
                if state_file.exists():
                    state_file.unlink()
                    cleaned_count += 1

                # Remove log files
                log_dir = generation_manager.state_dir / "logs"
                for log_file in log_dir.glob(f"{session['session_id']}_*.log"):
                    log_file.unlink(missing_ok=True)

            return {
                "success": True,
                "cleaned_sessions": cleaned_count,
                "message": f"Cleaned up {cleaned_count} old sessions",
            }

        except Exception as e:
            return {"error": f"Failed to cleanup sessions: {str(e)}"}

    @mcp.tool
    async def veo_download_video(
        session_id: Annotated[
            str,
            Field(
                description="Session ID returned from veo_generate_video",
            ),
        ],
        video_index: Annotated[
            Union[int, str],
            Field(
                default=0,
                description="Index of the video to download (for multiple samples, 0-based)",
            ),
        ] = 0,
        output_dir: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Directory to save the video. If not specified, uses default downloads directory.",
            ),
        ] = None,
    ) -> Dict[str, Any]:
        """
        Download a generated video from a completed generation session.

        Use this tool to:
        - Download videos after generation completes
        - Download a specific video from multiple samples
        - Re-download previously generated videos

        Note: Due to current SDK limitations, this downloads placeholder data.
        The actual video generation API requires allowlist access.

        Returns:
        - file_path: Path to the downloaded video file
        - file_size: Size of the downloaded file
        - success: Whether download was successful
        """
        try:
            # Parse parameters that might come as strings
            video_index = parse_int_param(video_index, default=0)

            # Check generation status
            status = generation_manager.get_status(session_id)

            if not status:
                return {"error": f"Session '{session_id}' not found", "success": False}

            if status.get("status") != "completed":
                return {
                    "error": f"Generation not complete. Current status: {status.get('status')}",
                    "success": False,
                }

            # Check if videos are available
            videos = status.get("videos", [])
            if not videos:
                return {
                    "error": "No videos found in completed generation",
                    "success": False,
                }

            if video_index >= len(videos):
                return {
                    "error": f"Video index {video_index} out of range. Only {len(videos)} videos available.",
                    "success": False,
                }

            # Check if already downloaded
            downloaded_videos = status.get("downloaded_videos", [])
            for dv in downloaded_videos:
                if dv.get("index") == video_index:
                    return {
                        "file_path": dv.get("file_path"),
                        "file_size": dv.get("file_size"),
                        "success": True,
                        "message": "Video already downloaded",
                    }

            # Get the video URI
            video = videos[video_index]
            video_uri = video.get("uri")

            if not video_uri:
                return {"error": "No video URI found for download", "success": False}

            # Prepare output path
            if output_dir:
                output_path = Path(output_dir)
            else:
                output_path = Path(config.config_dir) / "downloads" / session_id

            output_path.mkdir(parents=True, exist_ok=True)

            # Generate filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"veo_{session_id}_{video_index}_{timestamp}.mp4"
            full_path = output_path / filename

            # Initialize VeoClient and download
            try:
                veo_client = VeoClient(config.gemini_api_key, config.veo_model)

                # If the video URI is a file path (already downloaded), just copy it
                if video_uri.startswith("/") and Path(video_uri).exists():
                    import shutil

                    shutil.copy2(video_uri, full_path)
                    logger.info(f"Copied existing video from {video_uri} to {full_path}")
                else:
                    # Download from API using the SDK
                    logger.info(f"Downloading video from URI: {video_uri}")

                    # Extract file ID from URI
                    # URI format: https://generativelanguage.googleapis.com/v1beta/files/FILE_ID:download?alt=media
                    if "files/" in video_uri and ":download" in video_uri:
                        file_id = video_uri.split("files/")[1].split(":download")[0]
                        logger.info(f"Extracted file ID: {file_id}")

                        # Use the simplified download method
                        download_result = veo_client.download_video_by_file_id(file_id, str(full_path))

                        if download_result.get("error"):
                            return {"error": download_result["error"], "success": False}

                        logger.info(f"Downloaded video to {full_path} using SDK")
                    else:
                        return {
                            "error": f"Invalid video URI format: {video_uri}",
                            "success": False,
                        }

                # Get file size
                file_size = full_path.stat().st_size

                # Update status with download info
                downloaded_videos.append(
                    {
                        "index": video_index,
                        "file_path": str(full_path),
                        "file_size": file_size,
                    }
                )

                # Update the state file
                generation_manager._update_session_state(session_id, {"downloaded_videos": downloaded_videos})

                return {
                    "file_path": str(full_path),
                    "file_size": file_size,
                    "success": True,
                    "message": f"Video downloaded successfully to {full_path}",
                }

            except Exception as e:
                logger.error(f"Download failed: {e}")
                return {
                    "error": f"Failed to download video: {str(e)}",
                    "success": False,
                }

        except Exception as e:
            return {"error": f"Download error: {str(e)}", "success": False}

    return {
        "tools_registered": [
            "veo_generate_video",
            "veo_check_generation",
            "veo_download_video",
            "veo_list_sessions",
            "veo_cleanup_sessions",
        ]
    }
