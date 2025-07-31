"""Veo API client for video generation using Gemini API"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, Literal, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class VeoClient:
    """Client for Google Veo video generation using Gemini API"""

    def __init__(self, api_key: str, default_model: Optional[str] = None):
        """Initialize client with API key"""
        self.api_key = api_key
        self.default_model = default_model
        self.client = genai.Client(api_key=api_key)
        logger.debug(f"Initialized Veo client with model: {default_model}")

    def start_video_generation(
        self,
        prompt: str,
        model: Optional[str] = None,
        # Video generation parameters supported by SDK
        aspect_ratio: Literal["16:9", "9:16"] = "16:9",  # SDK only supports 16:9 and 9:16
        negative_prompt: Optional[str] = None,
        person_generation: Literal["dont_allow", "allow_adult"] = "allow_adult",  # SDK supports these values
        resolution: Optional[Literal["720p", "1080p"]] = None,
        number_of_videos: int = 1,  # SDK parameter
        duration_seconds: Optional[int] = None,  # SDK supports this
        seed: Optional[int] = None,
        enhance_prompt: bool = False,
        generate_audio: bool = False,
        output_gcs_uri: Optional[str] = None,  # SDK parameter for storage
        fps: Optional[int] = None,  # SDK parameter
    ) -> Dict[str, Any]:
        """
        Start video generation and return operation info.

        Uses the google-genai SDK's generate_videos method.
        """
        try:
            # Model name is already normalized by Config
            model_to_use = model or self.default_model

            # Log the attempt
            logger.info(f"Starting video generation with model: {model_to_use}")
            logger.info(f"Prompt: {prompt}")

            # Build config for video generation using all supported SDK parameters
            config_params = {
                "number_of_videos": number_of_videos,
            }

            # Add optional parameters that are supported by the SDK
            if enhance_prompt:
                config_params["enhance_prompt"] = enhance_prompt
            if generate_audio:
                config_params["generate_audio"] = generate_audio
            if negative_prompt:
                config_params["negative_prompt"] = negative_prompt
            if aspect_ratio:
                config_params["aspect_ratio"] = aspect_ratio
            if resolution:
                config_params["resolution"] = resolution
            if person_generation:
                config_params["person_generation"] = person_generation
            if duration_seconds is not None:
                config_params["duration_seconds"] = duration_seconds
            if seed is not None:
                config_params["seed"] = seed
            if output_gcs_uri:
                config_params["output_gcs_uri"] = output_gcs_uri
            if fps is not None:
                config_params["fps"] = fps

            # Create config object
            video_config = types.GenerateVideosConfig(**config_params)

            # Start video generation
            operation = self.client.models.generate_videos(model=model_to_use, prompt=prompt, config=video_config)

            return {
                "operation": operation,
                "done": False,
                "model": model_to_use,
                "prompt": prompt,
            }

        except Exception as e:
            logger.error(f"Video generation error: {type(e).__name__}: {str(e)}")
            return {
                "error": f"Failed to start video generation: {str(e)}",
                "done": True,
            }

    def get_operation_status(self, operation_name: str) -> Dict[str, Any]:
        """
        Check the status of a video generation operation.

        Uses the SDK's operations.get method.
        """
        try:
            # Get operation using the operations API
            operation = self.client.operations.get(operation=operation_name)

            result = {
                "operation_name": (operation.name if hasattr(operation, "name") else operation_name),
                "done": operation.done,
                "operation": operation,  # Store the operation object for later use
            }

            if operation.done:
                # Check for error
                if hasattr(operation, "error") and operation.error:
                    result["error"] = str(operation.error)
                # Extract videos from result
                elif hasattr(operation, "result") and hasattr(operation.result, "generated_videos"):
                    videos = []
                    for i, generated_video in enumerate(operation.result.generated_videos):
                        video_uri = None
                        if hasattr(generated_video.video, "uri"):
                            video_uri = generated_video.video.uri
                        elif hasattr(generated_video.video, "name"):
                            video_uri = generated_video.video.name

                        videos.append(
                            {
                                "index": i,
                                "uri": video_uri,
                                "mime_type": "video/mp4",
                            }
                        )

                    result["videos"] = videos
                    result["video_count"] = len(videos)

            return result

        except Exception as e:
            logger.error(f"Operation status error: {type(e).__name__}: {str(e)}")
            return {"error": f"Failed to get operation status: {str(e)}", "done": True}

    def poll_until_complete(self, operation, progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        Poll an operation until completion using native SDK components.
        """
        try:
            logger.info("Polling operation for completion...")
            start_time = time.time()
            max_wait_time = 600  # 10 minutes

            while True:
                # Get operation status using native SDK
                operation = self.client.operations.get(operation=operation)

                if operation.done:
                    # Check for errors
                    if hasattr(operation, "error") and operation.error:
                        error_msg = f"Generation failed: {operation.error}"
                        if progress_callback:
                            progress_callback({"status": "failed", "error": error_msg})
                        return {"error": error_msg, "success": False}

                    # Success - extract videos
                    try:
                        generated_videos = operation.result.generated_videos
                        if not generated_videos:
                            return {"error": "No videos generated", "success": False}

                        videos = []
                        for i, generated_video in enumerate(generated_videos):
                            video = generated_video.video
                            video_uri = None
                            if hasattr(video, "uri"):
                                video_uri = video.uri
                            elif hasattr(video, "name"):
                                video_uri = video.name

                            videos.append(
                                {
                                    "index": i,
                                    "uri": video_uri,
                                    "mime_type": "video/mp4",
                                    "downloaded": False,
                                }
                            )

                        return {
                            "success": True,
                            "videos": videos,
                            "video_count": len(videos),
                        }

                    except Exception as e:
                        logger.error(f"Error accessing video results: {e}")
                        return {
                            "error": f"Failed to access video results: {str(e)}",
                            "success": False,
                        }

                # Check timeout
                elapsed = time.time() - start_time
                if elapsed > max_wait_time:
                    if progress_callback:
                        progress_callback(
                            {
                                "status": "failed",
                                "error": f"Timeout after {max_wait_time} seconds",
                            }
                        )
                    return {
                        "error": f"Timeout after {max_wait_time} seconds",
                        "success": False,
                    }

                # Update progress
                if progress_callback:
                    progress_callback(
                        {
                            "status": "polling",
                            "progress": f"waiting for completion... ({int(elapsed)}s elapsed)",
                        }
                    )

                logger.debug(f"Waiting... ({int(elapsed)}s elapsed)")
                time.sleep(20)  # Poll every 20 seconds as per SDK examples

        except Exception as e:
            logger.error(f"Polling failed: {e}")
            return {"error": f"Polling failed: {str(e)}", "success": False}

    def download_video_by_file_id(self, file_id: str, output_path: str) -> Dict[str, Any]:
        """
        Download a video using native SDK components by file ID.
        """
        try:
            # Ensure output directory exists
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            # Get the file object using native SDK
            file_obj = self.client.files.get(name=f"files/{file_id}")

            # Download using native SDK - this returns bytes
            video_bytes = self.client.files.download(file=file_obj)

            # Write bytes to disk
            with open(output_path, "wb") as f:
                f.write(video_bytes)

            # Get file size
            file_size = Path(output_path).stat().st_size

            logger.info(f"Downloaded video to {output_path} ({file_size} bytes)")

            return {
                "file_path": output_path,
                "file_size": file_size,
                "success": True,
            }

        except Exception as e:
            logger.error(f"Download error: {type(e).__name__}: {str(e)}")
            return {"error": f"Failed to download video: {str(e)}", "success": False}
