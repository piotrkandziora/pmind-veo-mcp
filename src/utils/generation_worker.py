#!/usr/bin/env python3
"""Worker script for generating videos with Veo in the background"""

import argparse
import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from src.config import Config
from src.utils.veo_client import VeoClient

# Configure logging for the worker
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)


class GenerationWorker:
    """Handles Veo video generation with progress tracking"""

    def __init__(self, session_id: str, state_dir: str):
        self.session_id = session_id
        self.state_dir = Path(state_dir)
        self.state_file = self.state_dir / f"{session_id}.json"
        self.interrupted = False

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle termination signals"""
        self.interrupted = True
        self._update_state({"status": "cancelled", "error": "Generation interrupted"})
        sys.exit(0)

    def _read_state(self) -> Dict[str, Any]:
        """Read current state from file"""
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading state: {e}")
            return {}

    def _update_state(self, updates: Dict[str, Any]):
        """Update state file with new values atomically"""
        state = self._read_state()
        state.update(updates)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()

        temp_file = self.state_file.with_suffix(".tmp")
        try:
            # Write to temporary file first
            with open(temp_file, "w") as f:
                json.dump(state, f, indent=2)

            # Atomically replace the original file
            temp_file.replace(self.state_file)
        except Exception as e:
            logger.error(f"Error updating state: {e}")
            # Clean up temp file on error
            temp_file.unlink(missing_ok=True)

    async def generate(self, args):
        """Main generation process"""
        try:
            # Update status
            self._update_state(
                {
                    "status": "generating",
                    "progress": "starting generation",
                    "error": None,
                }
            )

            # Load configuration using Config class
            try:
                config = Config.from_env()
            except Exception as e:
                self._update_state(
                    {
                        "status": "failed",
                        "error": f"Failed to load configuration: {str(e)}",
                    }
                )
                return

            # Remove this error block - we'll try to use the SDK

            # Initialize Veo client with model from args or config
            model_to_use = args.model or config.veo_model
            veo_client = VeoClient(config.gemini_api_key, model_to_use)

            # Load input image if provided
            image_bytes = None
            image_mime_type = None
            if args.image_path:
                try:
                    # Check if file exists
                    if not Path(args.image_path).exists():
                        self._update_state(
                            {
                                "status": "failed",
                                "error": f"Input image not found: {args.image_path}",
                            }
                        )
                        return

                    # Read image bytes
                    with open(args.image_path, "rb") as f:
                        image_bytes = f.read()

                    # Determine mime type from extension
                    ext = Path(args.image_path).suffix.lower()
                    mime_map = {
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".png": "image/png",
                        ".gif": "image/gif",
                        ".webp": "image/webp",
                        ".bmp": "image/bmp",
                    }
                    image_mime_type = mime_map.get(ext, "image/jpeg")
                except Exception as e:
                    self._update_state(
                        {
                            "status": "failed",
                            "error": f"Failed to load input image: {str(e)}",
                        }
                    )
                    return

            # Start generation and download in one workflow
            self._update_state({"progress": "starting video generation"})

            # Determine output path if download requested
            if args.download_path:
                output_dir = Path(args.download_path)
                output_dir.mkdir(parents=True, exist_ok=True)

            # Step 1: Start video generation using native SDK
            self._update_state({"progress": "starting video generation"})

            generation_result = veo_client.start_video_generation(
                prompt=args.prompt,
                model=args.model,
                image_bytes=image_bytes,
                image_mime_type=image_mime_type,
                aspect_ratio=args.aspect_ratio,
                negative_prompt=args.negative_prompt,
                person_generation=args.person_generation,
                resolution=args.resolution,
                number_of_videos=args.number_of_videos,
                duration_seconds=args.duration_seconds,
                seed=args.seed,
                enhance_prompt=args.enhance_prompt,
                generate_audio=args.generate_audio,
                output_gcs_uri=args.output_gcs_uri,
                fps=args.fps,
            )

            if generation_result.get("error"):
                self._update_state(
                    {
                        "status": "failed",
                        "error": generation_result["error"],
                    }
                )
                return

            # Get the operation from the generation result
            operation = generation_result.get("operation")
            if not operation:
                self._update_state(
                    {
                        "status": "failed",
                        "error": "No operation returned from video generation",
                    }
                )
                return

            self._update_state(
                {
                    "status": "polling",
                    "progress": "video generation started, polling for completion",
                }
            )

            # Step 2: Poll until completion using native SDK
            def progress_callback(progress_info):
                updates = {}
                if "status" in progress_info:
                    updates["status"] = progress_info["status"]
                if "progress" in progress_info:
                    updates["progress"] = progress_info["progress"]
                if "error" in progress_info:
                    updates["error"] = progress_info["error"]

                if updates:
                    self._update_state(updates)

            result = veo_client.poll_until_complete(operation, progress_callback)

            # Check result
            if result.get("error"):
                self._update_state(
                    {
                        "status": "failed",
                        "error": result["error"],
                    }
                )
                return

            if result.get("success"):
                # Video generation completed successfully
                videos = result.get("videos", [])

                # Update state with video information
                state_update = {
                    "status": "completed",
                    "progress": "generation completed",
                    "videos": videos,
                    "video_count": result.get("video_count", len(videos)),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }

                self._update_state(state_update)

                logger.info("Video generation completed successfully")
                return
            else:
                # Unexpected result
                self._update_state(
                    {
                        "status": "failed",
                        "error": "Unexpected result from video generation",
                    }
                )
                return

        except Exception as e:
            self._update_state({"status": "failed", "error": str(e)})
            logger.error(f"Generation failed: {e}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Veo Video Generation Worker")
    parser.add_argument("--session-id", required=True, help="Generation session ID")
    parser.add_argument("--state-dir", required=True, help="State directory path")
    parser.add_argument("--prompt", help="Text prompt for generation")
    parser.add_argument(
        "--model",
        default=None,
        choices=["veo-2.0-generate-001", "veo-3.0-generate-preview", "veo-3.0-fast-generate-preview"],
        help="Model to use (defaults to VEO_MODEL from config)",
    )
    parser.add_argument("--aspect-ratio", default="16:9", choices=["16:9", "9:16"])
    parser.add_argument("--negative-prompt", default=None, help="Negative prompt")
    parser.add_argument(
        "--person-generation",
        default="allow_adult",
        choices=["allow_all", "allow_adult", "dont_allow"],
    )
    parser.add_argument("--resolution", default=None, choices=["720p", "1080p"])
    parser.add_argument("--number-of-videos", type=int, default=1)
    parser.add_argument("--duration-seconds", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--image-path", default=None, help="Path to input image for image-to-video")
    parser.add_argument("--enhance-prompt", action="store_true")
    parser.add_argument("--generate-audio", action="store_true")
    parser.add_argument("--output-gcs-uri", default=None, help="GCS URI for output storage")
    parser.add_argument("--fps", type=int, default=None, help="Frames per second")
    parser.add_argument("--download-path", default=None, help="Directory to download videos to")

    try:
        args = parser.parse_args()

        # Create worker and start generation
        worker = GenerationWorker(args.session_id, args.state_dir)

        # Run async main
        asyncio.run(worker.generate(args))
    except Exception as e:
        logger.error(f"Fatal error in worker main: {e}", exc_info=True)
        # Try to update state if possible
        try:
            state_file = Path(args.state_dir) / f"{args.session_id}.json"
            if state_file.exists():
                worker = GenerationWorker(args.session_id, args.state_dir)
                worker._update_state({"status": "failed", "error": f"Worker crashed: {str(e)}"})
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
