"""Generation Manager for handling background video generation processes"""

import json
import logging
import os
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


class GenerationManager:
    """Manages background video generation processes"""

    def __init__(self, state_dir: str = "/tmp/veo-generations"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _get_state_file(self, session_id: str) -> Path:
        """Get path to state file for a session"""
        return self.state_dir / f"{session_id}.json"

    def _read_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Read state from file"""
        state_file = self._get_state_file(session_id)
        if state_file.exists():
            try:
                with open(state_file, "r") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    def _write_state(self, session_id: str, state: Dict[str, Any]):
        """Write state to file atomically"""
        state_file = self._get_state_file(session_id)
        temp_file = state_file.with_suffix(".tmp")

        try:
            # Write to temporary file first
            with open(temp_file, "w") as f:
                json.dump(state, f, indent=2)

            # Atomically replace the original file
            # On POSIX systems, this is atomic
            temp_file.replace(state_file)
        except Exception:
            # Clean up temp file on error
            temp_file.unlink(missing_ok=True)
            raise

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process is still running"""
        try:
            # Check if process exists
            os.kill(pid, 0)
            # Verify it's actually our generation process
            try:
                proc = psutil.Process(pid)
                # Check if process is zombie
                if proc.status() == psutil.STATUS_ZOMBIE:
                    logger.warning(f"Process {pid} is a zombie, attempting to reap")
                    try:
                        os.waitpid(pid, os.WNOHANG)
                    except (OSError, ChildProcessError):
                        pass
                    return False
                cmdline = " ".join(proc.cmdline())
                return "generation_worker" in cmdline  # More flexible matching
            except psutil.NoSuchProcess:
                return False
            except Exception as e:
                logger.debug(f"Error checking process {pid}: {e}")
                return True  # Process exists but can't verify, assume it's ours
        except OSError:
            # Process doesn't exist, try to reap it if it's a zombie
            try:
                os.waitpid(pid, os.WNOHANG)
            except (OSError, ChildProcessError):
                pass
            return False

    def start_generation(
        self,
        prompt: str,
        model: str = "veo-2",
        aspect_ratio: str = "16:9",
        negative_prompt: Optional[str] = None,
        person_generation: str = "allow_adult",
        resolution: Optional[str] = None,
        number_of_videos: int = 1,
        duration_seconds: int = 8,
        seed: Optional[int] = None,
        enhance_prompt: bool = False,
        generate_audio: bool = False,
        output_gcs_uri: Optional[str] = None,
        fps: Optional[int] = None,
        download_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start a new generation process"""

        # Generate session ID
        session_id = f"gen_{uuid.uuid4().hex[:8]}_{int(time.time())}"
        logger.info(f"Starting new generation session: {session_id}")

        # Create initial state
        state = {
            "session_id": session_id,
            "status": "starting",
            "progress": "initializing subprocess",
            "prompt": prompt,
            "model": model,
            "number_of_videos": number_of_videos,
            "videos": [],
            "started_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "pid": None,
            "error": None,
            "generation_config": {
                "aspect_ratio": aspect_ratio,
                "person_generation": person_generation,
                "duration_seconds": duration_seconds,
                "number_of_videos": number_of_videos,
            },
        }

        if negative_prompt:
            state["generation_config"]["negative_prompt"] = negative_prompt
        if resolution:
            state["generation_config"]["resolution"] = resolution
        if seed is not None:
            state["generation_config"]["seed"] = seed
        if enhance_prompt:
            state["generation_config"]["enhance_prompt"] = enhance_prompt
        if generate_audio:
            state["generation_config"]["generate_audio"] = generate_audio
        if output_gcs_uri:
            state["generation_config"]["output_gcs_uri"] = output_gcs_uri
        if fps is not None:
            state["generation_config"]["fps"] = fps

        # Save initial state
        self._write_state(session_id, state)

        # Prepare command to run worker as a module (NO API KEY IN ARGS!)
        cmd = [
            sys.executable,
            "-m",
            "src.utils.generation_worker",
            "--session-id",
            session_id,
            "--state-dir",
            str(self.state_dir),
            "--prompt",
            prompt,
            "--model",
            model,
            "--aspect-ratio",
            aspect_ratio,
            "--person-generation",
            person_generation,
            "--number-of-videos",
            str(number_of_videos),
            "--duration-seconds",
            str(duration_seconds),
        ]

        if negative_prompt:
            cmd.extend(["--negative-prompt", negative_prompt])
        if resolution:
            cmd.extend(["--resolution", resolution])
        if seed is not None:
            cmd.extend(["--seed", str(seed)])
        if output_gcs_uri:
            cmd.extend(["--output-gcs-uri", output_gcs_uri])
        if enhance_prompt:
            cmd.append("--enhance-prompt")
        if generate_audio:
            cmd.append("--generate-audio")
        if fps is not None:
            cmd.extend(["--fps", str(fps)])
        if download_path:
            cmd.extend(["--download-path", download_path])

        # Start subprocess
        try:
            # Get project root directory (3 levels up from this file)
            project_root = Path(__file__).parent.parent.parent

            # Pass API key securely via environment
            env = os.environ.copy()
            # Get API key from Config
            from ..config import Config

            config = Config.from_env()
            env["GEMINI_API_KEY"] = config.gemini_api_key

            # Create log files for subprocess output
            log_dir = self.state_dir / "logs"
            log_dir.mkdir(exist_ok=True)
            stdout_log = open(log_dir / f"{session_id}_stdout.log", "w")
            stderr_log = open(log_dir / f"{session_id}_stderr.log", "w")

            proc = subprocess.Popen(
                cmd,
                stdout=stdout_log,
                stderr=stderr_log,
                start_new_session=True,  # Detach from parent process group
                cwd=str(project_root),  # Set working directory to project root
                env=env,  # Pass environment
            )

            # Close file handles in parent process
            stdout_log.close()
            stderr_log.close()

            # Update state with PID
            state["pid"] = proc.pid
            state["status"] = "running"
            state["progress"] = "subprocess started"
            self._write_state(session_id, state)
            logger.info(f"Started subprocess with PID {proc.pid} for session {session_id}")

            return {
                "session_id": session_id,
                "status": "started",
                "pid": proc.pid,
                "message": "Video generation started in background",
            }

        except Exception as e:
            logger.error(f"Failed to start generation subprocess: {e}")
            state["status"] = "failed"
            state["error"] = str(e)
            self._write_state(session_id, state)
            return {"session_id": session_id, "status": "failed", "error": str(e)}

    def get_status(self, session_id: str) -> Dict[str, Any]:
        """Get status of a generation"""
        state = self._read_state(session_id)

        if not state:
            return {"error": "Generation session not found", "session_id": session_id}

        # Check if process is still running
        if state.get("pid") and state["status"] in ["running", "generating", "polling"]:
            if not self._is_process_running(state["pid"]):
                # Process died unexpectedly
                if state["status"] != "completed" and not state.get("error"):
                    state["status"] = "failed"
                    state["error"] = "Generation process terminated unexpectedly"
                    self._write_state(session_id, state)

        return state

    def list_generations(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """List all generation sessions"""
        generations = []

        for state_file in self.state_dir.glob("gen_*.json"):
            session_id = state_file.stem
            state = self._read_state(session_id)

            if state:
                # Update status for running processes
                if state.get("pid") and state["status"] in [
                    "running",
                    "generating",
                    "polling",
                ]:
                    if not self._is_process_running(state["pid"]):
                        state["status"] = "failed" if state["status"] != "completed" else state["status"]

                if not active_only or state["status"] in [
                    "running",
                    "generating",
                    "polling",
                    "starting",
                ]:
                    generations.append(state)

        # Sort by start time, newest first
        generations.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return generations

    def cancel_generation(self, session_id: str) -> Dict[str, Any]:
        """Cancel a generation"""
        state = self._read_state(session_id)

        if not state:
            return {"error": "Generation session not found", "session_id": session_id}

        if state["status"] not in ["running", "generating", "polling", "starting"]:
            return {
                "error": f"Cannot cancel generation in status: {state['status']}",
                "session_id": session_id,
                "status": state["status"],
            }

        # Try to terminate the process
        if state.get("pid"):
            pid = state["pid"]
            try:
                # Send SIGTERM for graceful shutdown
                os.kill(pid, signal.SIGTERM)
                logger.info(f"Sent SIGTERM to process {pid} for session {session_id}")

                # Wait up to 5 seconds for process to terminate
                for _ in range(50):
                    if not self._is_process_running(pid):
                        break
                    time.sleep(0.1)

                # Force kill if still running
                if self._is_process_running(pid):
                    os.kill(pid, signal.SIGKILL)
                    time.sleep(0.1)
                    logger.warning(f"Force killed process {pid} for session {session_id}")

                # Reap the process to prevent zombie
                try:
                    os.waitpid(pid, os.WNOHANG)
                except (OSError, ChildProcessError):
                    pass

            except OSError:
                pass  # Process already dead

        # Update state
        state["status"] = "cancelled"
        state["error"] = "Cancelled by user"
        state["updated_at"] = datetime.utcnow().isoformat() + "Z"
        self._write_state(session_id, state)

        return {
            "session_id": session_id,
            "status": "cancelled",
            "message": "Generation cancelled successfully",
        }

    def _update_session_state(self, session_id: str, updates: Dict[str, Any]):
        """Update specific fields in session state"""
        try:
            state = self._read_state(session_id)
            if state:
                state.update(updates)
                state["updated_at"] = datetime.utcnow().isoformat() + "Z"
                self._write_state(session_id, state)
        except Exception as e:
            logger.error(f"Failed to update session state: {e}")
