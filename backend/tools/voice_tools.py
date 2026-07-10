"""
Voice & Audio Intelligence Tools.

Gives the agent ears and a voice — 100% offline, no external APIs:
  - transcribe_audio      : Transcribe any audio/video file via local Whisper model
  - batch_transcribe      : Transcribe all audio files in a directory
  - text_to_speech        : Speak text aloud via local TTS (pyttsx3 / espeak)
  - save_speech_to_file   : Render TTS to a .wav file without playing it
  - audio_info            : Metadata for an audio file (duration, codec, bitrate, etc.)
  - list_audio_files      : Find audio/video files under a directory
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.base import Tool, ToolResult

# ── Supported extensions ─────────────────────────────────────────────────────

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma",
    ".opus", ".aiff", ".au", ".ra",
}
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
    ".ts", ".m2ts", ".mpeg", ".mpg",
}
ALL_MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


# ── Whisper helper ────────────────────────────────────────────────────────────

def _check_whisper():
    """Return (available: bool, module_name: str, note: str)."""
    try:
        import faster_whisper  # noqa: F401
        return True, "faster_whisper", ""
    except ImportError:
        pass
    try:
        import whisper  # noqa: F401
        return True, "whisper", ""
    except ImportError:
        pass
    return False, "", "Install faster-whisper or openai-whisper: pip install faster-whisper"


def _transcribe_sync(path: str, model_size: str, language: Optional[str]) -> Dict:
    """
    Blocking transcription call — runs in a thread via asyncio.to_thread.
    Tries faster_whisper first (memory-efficient), then openai-whisper.
    """
    available, mod_name, err = _check_whisper()
    if not available:
        return {"success": False, "error": err}

    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return {"success": False, "error": f"File not found: {path}"}

    try:
        if mod_name == "faster_whisper":
            from faster_whisper import WhisperModel
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            kwargs: Dict[str, Any] = {}
            if language:
                kwargs["language"] = language
            segments, info = model.transcribe(path, beam_size=5, **kwargs)
            text_parts = [seg.text.strip() for seg in segments]
            text = " ".join(text_parts)
            detected_lang = info.language
            duration = info.duration
            return {
                "success": True,
                "text": text,
                "language": detected_lang,
                "duration_seconds": round(duration, 2),
                "model": f"faster-whisper/{model_size}",
                "segments": len(text_parts),
            }
        else:
            import whisper
            model = whisper.load_model(model_size)
            options: Dict[str, Any] = {}
            if language:
                options["language"] = language
            result = model.transcribe(path, **options)
            return {
                "success": True,
                "text": result["text"].strip(),
                "language": result.get("language", "unknown"),
                "duration_seconds": round(result.get("duration", 0), 2),
                "model": f"openai-whisper/{model_size}",
                "segments": len(result.get("segments", [])),
            }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# ── TTS helpers ───────────────────────────────────────────────────────────────

def _tts_speak_sync(text: str, rate: int, volume: float, voice: str) -> Dict:
    """Speak text aloud using pyttsx3 (blocking)."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        engine.setProperty("volume", volume)
        if voice:
            for v in engine.getProperty("voices"):
                if voice.lower() in (v.id or "").lower() or voice.lower() in (v.name or "").lower():
                    engine.setProperty("voice", v.id)
                    break
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        return {"success": True, "engine": "pyttsx3", "chars": len(text)}
    except ImportError:
        pass

    # Fallback: espeak
    if shutil.which("espeak") or shutil.which("espeak-ng"):
        cmd = shutil.which("espeak-ng") or "espeak"
        args = [cmd, "-s", str(rate), "--", text]
        r = subprocess.run(args, capture_output=True, timeout=30)
        if r.returncode == 0:
            return {"success": True, "engine": "espeak", "chars": len(text)}
        return {"success": False, "error": r.stderr.decode(errors="replace")}

    # Fallback: festival
    if shutil.which("festival"):
        r = subprocess.run(["festival", "--tts"], input=text.encode(), capture_output=True, timeout=30)
        if r.returncode == 0:
            return {"success": True, "engine": "festival", "chars": len(text)}

    return {"success": False, "error": "No TTS engine found. Install pyttsx3, espeak, or festival."}


def _tts_save_sync(text: str, output: str, rate: int, voice: str) -> Dict:
    """Save speech to a .wav file (blocking)."""
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        if voice:
            for v in engine.getProperty("voices"):
                if voice.lower() in (v.id or "").lower() or voice.lower() in (v.name or "").lower():
                    engine.setProperty("voice", v.id)
                    break
        engine.save_to_file(text, output)
        engine.runAndWait()
        engine.stop()
        if os.path.exists(output) and os.path.getsize(output) > 0:
            return {"success": True, "engine": "pyttsx3", "path": output, "size": os.path.getsize(output)}
        return {"success": False, "error": "pyttsx3 produced empty output."}
    except ImportError:
        pass

    # Fallback: espeak to WAV
    if shutil.which("espeak") or shutil.which("espeak-ng"):
        cmd = shutil.which("espeak-ng") or "espeak"
        args = [cmd, "-s", str(rate), "-w", output, "--", text]
        r = subprocess.run(args, capture_output=True, timeout=30)
        if r.returncode == 0 and os.path.exists(output):
            return {"success": True, "engine": "espeak", "path": output, "size": os.path.getsize(output)}
        return {"success": False, "error": r.stderr.decode(errors="replace") or "espeak failed."}

    return {"success": False, "error": "No TTS engine found. Install pyttsx3 or espeak."}


def _audio_info_sync(path: str) -> Dict:
    """Get audio/video metadata using ffprobe or mutagen (blocking)."""
    path = os.path.expanduser(path)
    if not os.path.exists(path):
        return {"success": False, "error": f"File not found: {path}"}

    # Try ffprobe (most comprehensive)
    if shutil.which("ffprobe"):
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            path,
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=15)
        if r.returncode == 0:
            try:
                meta = json.loads(r.stdout.decode())
                fmt = meta.get("format", {})
                streams = meta.get("streams", [])
                audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
                video_streams = [s for s in streams if s.get("codec_type") == "video"]
                info: Dict[str, Any] = {
                    "path": path,
                    "filename": os.path.basename(path),
                    "size_bytes": int(fmt.get("size", 0)),
                    "duration_seconds": round(float(fmt.get("duration", 0)), 2),
                    "bitrate_kbps": round(int(fmt.get("bit_rate", 0)) / 1000),
                    "format": fmt.get("format_long_name", fmt.get("format_name", "")),
                    "tags": fmt.get("tags", {}),
                    "audio_streams": [
                        {
                            "codec": s.get("codec_name"),
                            "channels": s.get("channels"),
                            "sample_rate": s.get("sample_rate"),
                            "bit_rate": s.get("bit_rate"),
                        }
                        for s in audio_streams
                    ],
                    "video_streams": [
                        {
                            "codec": s.get("codec_name"),
                            "width": s.get("width"),
                            "height": s.get("height"),
                            "fps": s.get("r_frame_rate"),
                        }
                        for s in video_streams
                    ],
                    "has_video": len(video_streams) > 0,
                    "source": "ffprobe",
                }
                return {"success": True, **info}
            except Exception:
                pass

    # Fallback: mutagen
    try:
        from mutagen import File as MutagenFile
        mf = MutagenFile(path)
        if mf is not None:
            info = {
                "path": path,
                "filename": os.path.basename(path),
                "size_bytes": os.path.getsize(path),
                "duration_seconds": round(getattr(mf.info, "length", 0), 2),
                "bitrate_kbps": round(getattr(mf.info, "bitrate", 0) / 1000)
                    if hasattr(mf.info, "bitrate") else None,
                "tags": {k: str(v) for k, v in (mf.tags or {}).items()},
                "source": "mutagen",
            }
            return {"success": True, **info}
    except ImportError:
        pass
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    # Minimal fallback: just file size + extension
    stat = os.stat(path)
    return {
        "success": True,
        "path": path,
        "filename": os.path.basename(path),
        "size_bytes": stat.st_size,
        "source": "os.stat (no media parser available)",
    }


# ══════════════════════════════════════════════════════════════════════════════
# Tool classes
# ══════════════════════════════════════════════════════════════════════════════


class TranscribeAudioTool(Tool):
    """Transcribe a single audio or video file using a local Whisper model."""

    name = "transcribe_audio"
    description = (
        "Transcribe an audio or video file to text using a local Whisper model "
        "(100% offline, no API key needed). Supports MP3, WAV, FLAC, OGG, M4A, "
        "MP4, MKV, and most other formats."
    )
    parameters_schema = {
        "path":       "Absolute path to the audio or video file.",
        "model":      "(optional) Whisper model size: 'tiny', 'base', 'small', 'medium', 'large'. Default 'base'.",
        "language":   "(optional) Force a language code, e.g. 'en', 'hi', 'fr'. Auto-detected if omitted.",
        "save_to":    "(optional) If provided, save the transcript to this .txt file path.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path      = os.path.expanduser(args.get("path", ""))
        model     = args.get("model", "base")
        language  = args.get("language") or None
        save_to   = args.get("save_to") or None

        if not path:
            return ToolResult(success=False, message="'path' is required.")

        result = await asyncio.to_thread(_transcribe_sync, path, model, language)

        if not result["success"]:
            return ToolResult(success=False, message=result["error"])

        text = result["text"]

        # Optionally save transcript
        saved_path = None
        if save_to:
            save_to = os.path.expanduser(save_to)
            try:
                os.makedirs(os.path.dirname(os.path.abspath(save_to)), exist_ok=True)
                with open(save_to, "w", encoding="utf-8") as fh:
                    fh.write(f"# Transcript: {os.path.basename(path)}\n")
                    fh.write(f"# Transcribed: {datetime.now().isoformat()}\n")
                    fh.write(f"# Model: {result.get('model')}\n")
                    fh.write(f"# Language: {result.get('language')}\n\n")
                    fh.write(text)
                saved_path = save_to
            except Exception as exc:
                result["save_error"] = str(exc)

        return ToolResult(
            success=True,
            data={
                "transcript": text,
                "language":   result.get("language", "unknown"),
                "duration_s": result.get("duration_seconds"),
                "model":      result.get("model"),
                "segments":   result.get("segments"),
                "saved_to":   saved_path,
                "source_file": path,
            },
            message=(
                f"Transcribed '{os.path.basename(path)}' "
                f"({result.get('duration_seconds', '?')}s, "
                f"lang={result.get('language', '?')})."
                + (f" Saved to {saved_path}" if saved_path else "")
            ),
            files_affected=[path] + ([saved_path] if saved_path else []),
        )


class BatchTranscribeTool(Tool):
    """Transcribe all audio/video files in a directory."""

    name = "batch_transcribe"
    description = (
        "Transcribe all audio/video files in a directory using a local Whisper model. "
        "Each transcript is saved as a .txt file alongside the original."
    )
    parameters_schema = {
        "path":      "Absolute path to the directory containing audio/video files.",
        "model":     "(optional) Whisper model: 'tiny', 'base', 'small', 'medium', 'large'. Default 'base'.",
        "language":  "(optional) Force a language code. Auto-detected if omitted.",
        "recursive": "(optional) Search subdirectories. Default false.",
        "output_dir":"(optional) Directory to save transcripts. Defaults to same directory as audio file.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        dir_path   = os.path.expanduser(args.get("path", ""))
        model      = args.get("model", "base")
        language   = args.get("language") or None
        recursive  = args.get("recursive", False)
        output_dir = os.path.expanduser(args.get("output_dir", "")) if args.get("output_dir") else None

        if not dir_path or not os.path.isdir(dir_path):
            return ToolResult(success=False, message=f"Directory not found: {dir_path}")

        # Collect files
        files: List[Path] = []
        root = Path(dir_path)
        glob = "**/*" if recursive else "*"
        for p in root.glob(glob):
            if p.is_file() and p.suffix.lower() in ALL_MEDIA_EXTENSIONS:
                files.append(p)

        if not files:
            return ToolResult(
                success=True,
                data={"transcribed": 0, "files": []},
                message="No audio/video files found.",
            )

        results = []
        for fp in files:
            dest_dir = output_dir or str(fp.parent)
            save_to  = os.path.join(dest_dir, fp.stem + "_transcript.txt")
            res = await asyncio.to_thread(_transcribe_sync, str(fp), model, language)
            if res["success"]:
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                    with open(save_to, "w", encoding="utf-8") as fh:
                        fh.write(f"# Transcript: {fp.name}\n")
                        fh.write(f"# Transcribed: {datetime.now().isoformat()}\n\n")
                        fh.write(res["text"])
                    results.append({
                        "file": str(fp),
                        "transcript": save_to,
                        "language": res.get("language"),
                        "duration_s": res.get("duration_seconds"),
                    })
                except Exception as exc:
                    results.append({"file": str(fp), "error": str(exc)})
            else:
                results.append({"file": str(fp), "error": res["error"]})

        ok_count = sum(1 for r in results if "transcript" in r)
        return ToolResult(
            success=True,
            data={"transcribed": ok_count, "total": len(files), "files": results},
            message=f"Transcribed {ok_count}/{len(files)} files.",
            files_affected=[r["transcript"] for r in results if "transcript" in r],
        )


class TextToSpeechTool(Tool):
    """Speak text aloud using a local TTS engine (pyttsx3 / espeak)."""

    name = "text_to_speech"
    description = (
        "Speak text aloud using a local, offline TTS engine. "
        "Uses pyttsx3 if available, otherwise falls back to espeak / festival."
    )
    parameters_schema = {
        "text":   "The text to speak.",
        "rate":   "(optional) Words-per-minute speaking rate. Default 175.",
        "volume": "(optional) Volume level 0.0–1.0. Default 1.0.",
        "voice":  "(optional) Partial match for voice name/ID (e.g. 'female', 'en'). Uses default if not found.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        text   = args.get("text", "")
        rate   = int(args.get("rate", 175))
        volume = float(args.get("volume", 1.0))
        voice  = args.get("voice", "")

        if not text:
            return ToolResult(success=False, message="'text' is required.")

        res = await asyncio.to_thread(_tts_speak_sync, text, rate, volume, voice)
        if res["success"]:
            return ToolResult(
                success=True,
                data=res,
                message=f"Spoke {res['chars']} characters via {res['engine']}.",
            )
        return ToolResult(success=False, message=res["error"])


class SaveSpeechToFileTool(Tool):
    """Render text to a speech audio file without playing it."""

    name = "save_speech_to_file"
    description = (
        "Convert text to speech and save the result as a .wav audio file "
        "using a local, offline TTS engine. Useful for generating voice alerts, "
        "notifications, or audio summaries of documents."
    )
    parameters_schema = {
        "text":   "The text to convert to speech.",
        "output": "Destination .wav file path.",
        "rate":   "(optional) Words-per-minute speaking rate. Default 175.",
        "voice":  "(optional) Partial match for voice name/ID.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        text   = args.get("text", "")
        output = os.path.expanduser(args.get("output", ""))
        rate   = int(args.get("rate", 175))
        voice  = args.get("voice", "")

        if not text:
            return ToolResult(success=False, message="'text' is required.")
        if not output:
            # Default to ~/Music/aegis_speech_<timestamp>.wav
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output = os.path.expanduser(f"~/Music/aegis_speech_{ts}.wav")

        res = await asyncio.to_thread(_tts_save_sync, text, output, rate, voice)
        if res["success"]:
            return ToolResult(
                success=True,
                data=res,
                message=f"Speech saved to {res['path']} ({res.get('size', 0)} bytes).",
                files_affected=[res["path"]],
            )
        return ToolResult(success=False, message=res["error"])


class AudioInfoTool(Tool):
    """Get detailed metadata for an audio or video file."""

    name = "audio_info"
    description = (
        "Get technical metadata for an audio or video file: duration, codec, "
        "bitrate, sample rate, channels, embedded tags (artist, album, title, etc.). "
        "Uses ffprobe if available, otherwise mutagen."
    )
    parameters_schema = {
        "path": "Absolute path to the audio or video file.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        if not path:
            return ToolResult(success=False, message="'path' is required.")

        res = await asyncio.to_thread(_audio_info_sync, path)
        if res.pop("success"):
            return ToolResult(
                success=True,
                data=res,
                message=f"Metadata retrieved for {os.path.basename(path)}.",
            )
        return ToolResult(success=False, message=res.get("error", "Failed to read metadata."))


class ListAudioFilesTool(Tool):
    """Find audio and video files in a directory."""

    name = "list_audio_files"
    description = (
        "List all audio and video files in a directory. "
        "Returns file name, size, and last-modified date."
    )
    parameters_schema = {
        "path":           "Absolute path to the directory to search.",
        "recursive":      "(optional) Search subdirectories. Default false.",
        "include_video":  "(optional) Include video files in results. Default true.",
        "include_audio":  "(optional) Include audio files in results. Default true.",
        "max_results":    "(optional) Maximum number of files to return. Default 200.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        dir_path      = os.path.expanduser(args.get("path", ""))
        recursive     = args.get("recursive", False)
        include_video = args.get("include_video", True)
        include_audio = args.get("include_audio", True)
        max_results   = int(args.get("max_results", 200))

        if not dir_path or not os.path.isdir(dir_path):
            return ToolResult(success=False, message=f"Directory not found: {dir_path}")

        allowed_exts = set()
        if include_audio:
            allowed_exts |= AUDIO_EXTENSIONS
        if include_video:
            allowed_exts |= VIDEO_EXTENSIONS

        files: List[Dict] = []
        root = Path(dir_path)
        glob = "**/*" if recursive else "*"
        for p in root.glob(glob):
            if p.is_file() and p.suffix.lower() in allowed_exts:
                try:
                    stat = p.stat()
                    files.append({
                        "path":     str(p),
                        "name":     p.name,
                        "size":     stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "type":     "video" if p.suffix.lower() in VIDEO_EXTENSIONS else "audio",
                        "ext":      p.suffix.lower(),
                    })
                except Exception:
                    pass
            if len(files) >= max_results:
                break

        files.sort(key=lambda f: f["modified"], reverse=True)
        return ToolResult(
            success=True,
            data={"files": files, "total": len(files)},
            message=f"Found {len(files)} media file(s) in {dir_path}.",
        )


# ── Registry ──────────────────────────────────────────────────────────────────

ALL_VOICE_TOOLS = [
    TranscribeAudioTool(),
    BatchTranscribeTool(),
    TextToSpeechTool(),
    SaveSpeechToFileTool(),
    AudioInfoTool(),
    ListAudioFilesTool(),
]
