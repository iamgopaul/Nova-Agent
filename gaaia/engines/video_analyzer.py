"""Video analysis tool for analyzing video content from URLs and local files."""
from __future__ import annotations

import base64
import io
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests

from gaaia.tools.base import BaseTool, ToolResult


class AnalyzeVideoTool(BaseTool):
    """Analyze video content: extract frames, detect scenes, read text, identify objects."""

    name = "analyze_video"
    description = (
        "Analyze video content from YouTube links, online videos, or local files. "
        "Extracts key frames and uses AI vision to provide scene descriptions, "
        "detect text, identify objects, and summarize content. "
        "Supports YouTube URLs, direct video links, and local file paths."
    )

    def schema(self) -> dict:
        return self._schema(
            {
                "type": "object",
                "properties": {
                    "video_source": {
                        "type": "string",
                        "description": (
                            "YouTube URL, direct video link (mp4/webm/mov), "
                            "or local file path to video file."
                        ),
                    },
                    "frame_count": {
                        "type": "integer",
                        "description": "Number of key frames to extract (default 5, max 20).",
                    },
                    "analysis_focus": {
                        "type": "string",
                        "enum": ["general", "text", "objects", "all"],
                        "description": (
                            "general=scenes & content, text=read captions/text, "
                            "objects=detect entities, all=comprehensive analysis"
                        ),
                    },
                },
                "required": ["video_source"],
            }
        )

    async def run(
        self,
        video_source: str,
        frame_count: int = 5,
        analysis_focus: str = "all",
    ) -> ToolResult:
        """Analyze video content."""
        try:
            frame_count = max(1, min(frame_count, 20))

            # Step 1: Get video file (download if needed)
            video_path = await self._get_video_file(video_source)
            if not video_path:
                return ToolResult(
                    content=f"Could not access video: {video_source}",
                    error="Video access failed",
                )

            # Step 2: Extract frames
            frames = await self._extract_frames(video_path, frame_count)
            if not frames:
                return ToolResult(
                    content="Could not extract frames from video",
                    error="Frame extraction failed",
                )

            # Step 3: Analyze frames with AI vision
            analysis = await self._analyze_frames(
                frames, analysis_focus
            )

            # Clean up temp video file if downloaded
            if video_source.startswith(("http://", "https://")) or video_source.startswith("youtube"):
                try:
                    os.remove(video_path)
                except Exception:
                    pass

            return ToolResult(
                content=analysis,
                metadata={
                    "frames_extracted": len(frames),
                    "video_source": video_source,
                    "analysis_type": analysis_focus,
                },
            )

        except Exception as exc:
            return ToolResult(
                content=f"Video analysis failed: {str(exc)}",
                error=str(exc),
            )

    async def _get_video_file(self, source: str) -> str | None:
        """Download or locate video file. Returns path to video file."""
        # Check if it's a local file
        if os.path.isfile(source):
            return source

        # YouTube URL
        if "youtube.com" in source or "youtu.be" in source:
            return await self._download_youtube(source)

        # Direct video URL
        if source.startswith(("http://", "https://")):
            return await self._download_video(source)

        return None

    async def _download_youtube(self, url: str) -> str | None:
        """Download YouTube video. Returns temp file path."""
        try:
            import yt_dlp

            temp_dir = tempfile.gettempdir()
            output_path = os.path.join(temp_dir, "gaaia_video_%(id)s.mp4")

            opts = {
                "format": "best[height<=480]",
                "quiet": False,
                "outtmpl": output_path,
                "socket_timeout": 30,
            }

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                video_file = ydl.prepare_filename(info)
                return video_file if os.path.isfile(video_file) else None

        except ImportError:
            return None
        except Exception:
            return None

    async def _download_video(self, url: str) -> str | None:
        """Download video from direct URL. Returns temp file path."""
        try:
            resp = requests.get(url, timeout=30, stream=True)
            if resp.status_code != 200:
                return None

            suffix = self._get_extension_from_url(url) or ".mp4"
            temp_file = tempfile.NamedTemporaryFile(
                suffix=suffix, delete=False
            )
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)
            temp_file.close()
            return temp_file.name if os.path.getsize(temp_file.name) > 0 else None

        except Exception:
            return None

    def _get_extension_from_url(self, url: str) -> str | None:
        """Extract file extension from URL."""
        path = urlparse(url).path
        for ext in [".mp4", ".webm", ".mov", ".avi", ".mkv"]:
            if ext in path.lower():
                return ext
        return None

    async def _extract_frames(self, video_path: str, count: int) -> list[str]:
        """Extract key frames from video. Returns list of base64-encoded images."""
        try:
            # Get video duration
            duration_cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1:novalue=1",
                video_path,
            ]
            duration_result = subprocess.run(
                duration_cmd, capture_output=True, text=True, timeout=10
            )
            try:
                duration = float(duration_result.stdout.strip())
            except (ValueError, AttributeError):
                duration = 30  # Fallback

            # Calculate frame timestamps
            timestamps = []
            if duration > 0:
                interval = duration / (count + 1)
                timestamps = [interval * (i + 1) for i in range(count)]
            else:
                timestamps = [i * 5 for i in range(count)]

            frames_b64 = []
            temp_dir = tempfile.gettempdir()

            for i, ts in enumerate(timestamps):
                frame_path = os.path.join(temp_dir, f"frame_{i}.jpg")
                extract_cmd = [
                    "ffmpeg",
                    "-ss",
                    str(ts),
                    "-i",
                    video_path,
                    "-vf",
                    "scale=640:360",
                    "-vframes",
                    "1",
                    "-q:v",
                    "2",
                    "-y",
                    frame_path,
                ]

                subprocess.run(
                    extract_cmd,
                    capture_output=True,
                    timeout=10,
                )

                if os.path.isfile(frame_path):
                    with open(frame_path, "rb") as f:
                        frame_b64 = base64.b64encode(f.read()).decode()
                        frames_b64.append(frame_b64)
                    try:
                        os.remove(frame_path)
                    except Exception:
                        pass

            return frames_b64

        except Exception:
            return []

    async def _analyze_frames(
        self, frames: list[str], focus: str
    ) -> str:
        """Analyze frames using local Ollama vision model."""
        if not frames:
            return "No frames to analyze."
        return await self._local_frame_analysis(frames, focus)

    async def _local_frame_analysis(
        self, frames: list[str], focus: str
    ) -> str:
        """Analyze frames with the local Ollama vision model (llama3.2-vision)."""
        from gaaia.services.model_client import get_model_client

        prompts = {
            "general": "Describe what you see in these video frames. Summarise the scenes, actions, and overall context.",
            "text": "Carefully read and extract all visible text, captions, titles, and labels from these frames.",
            "objects": "Identify and describe all visible objects, people, logos, and entities in these frames.",
            "all": (
                "Provide a comprehensive analysis: "
                "1) Scene descriptions and narrative; "
                "2) All visible text and captions; "
                "3) Key objects, people, and entities; "
                "4) Overall content summary."
            ),
        }
        prompt = prompts.get(focus, prompts["all"])

        try:
            client = get_model_client(host="http://localhost:11434", timeout=180.0)
            content = client.chat(
                model="llama3.2-vision:11b",
                messages=[{"role": "user", "content": prompt, "images": frames}],
            )
            return content or "No response from vision model."
        except Exception as exc:
            return f"Vision analysis failed: {exc}\n\nMake sure `llama3.2-vision:11b` is pulled in Ollama."
