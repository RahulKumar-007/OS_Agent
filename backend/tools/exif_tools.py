"""
EXIF Tools.
Extract metadata from images (date taken, camera info, GPS).
"""

import os
from datetime import datetime
from typing import Dict

from tools.base import Tool, ToolResult

HAS_PIL = False
HAS_PIEXIF = False

try:
    from PIL import Image
    from PIL.ExifTags import TAGS

    HAS_PIL = True
except ImportError:
    pass

try:
    import piexif

    HAS_PIEXIF = True
except ImportError:
    pass


class ExtractEXIFTool(Tool):
    name = "extract_exif"
    description = "Extract EXIF metadata from images (date taken, camera, GPS)"
    parameters_schema = {
        "path": "Image file path",
    }

    async def execute(self, args: Dict) -> ToolResult:
        if not HAS_PIL:
            return ToolResult(success=False, message="PIL not installed")

        path = os.path.expanduser(args.get("path", ""))

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"File not found: {path}")

        try:
            img = Image.open(path)
            exif_data = img._getexif()

            if not exif_data:
                return ToolResult(
                    success=True,
                    data={"exif": {}, "has_exif": False},
                    message="No EXIF data",
                )

            # Parse EXIF
            exif = {}
            for tag_id, value in exif_data.items():
                tag = TAGS.get(tag_id, tag_id)
                exif[tag] = str(value)

            # Extract key fields
            date_taken = exif.get("DateTimeOriginal") or exif.get("DateTime")
            camera = exif.get("Model")

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "date_taken": date_taken,
                    "camera": camera,
                    "exif": exif,
                    "has_exif": True,
                },
                message=f"EXIF data extracted",
                files_affected=[path],
            )

        except Exception as e:
            return ToolResult(
                success=False, message=f"EXIF extraction failed: {str(e)}"
            )


class BatchRenameByEXIFTool(Tool):
    name = "batch_rename_by_exif"
    description = "Rename images using EXIF date (e.g., IMG_20240615_143052.jpg)"
    parameters_schema = {
        "path": "Directory containing images",
        "format": "(optional) Date format: 'YYYYMMDD_HHMMSS', 'YYYY-MM-DD', 'YYYYMMDD'. Default 'YYYYMMDD_HHMMSS'.",
        "prefix": "(optional) Prefix for new names. Default 'IMG_'.",
        "dry_run": "(optional) Preview only. Default true.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        if not HAS_PIL:
            return ToolResult(success=False, message="PIL not installed")

        dir_path = os.path.expanduser(args.get("path", ""))
        date_format = args.get("format", "YYYYMMDD_HHMMSS")
        prefix = args.get("prefix", "IMG_")
        dry_run = args.get("dry_run", True)

        if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
            return ToolResult(success=False, message=f"Invalid directory: {dir_path}")

        # Find images
        image_exts = {".jpg", ".jpeg", ".png", ".tiff", ".heic"}
        renames = []
        skipped = []

        for fname in os.listdir(dir_path):
            fpath = os.path.join(dir_path, fname)
            if not os.path.isfile(fpath):
                continue

            ext = os.path.splitext(fname)[1].lower()
            if ext not in image_exts:
                continue

            try:
                img = Image.open(fpath)
                exif_data = img._getexif()

                if not exif_data:
                    skipped.append({"file": fname, "reason": "No EXIF data"})
                    continue

                # Get date
                exif = {}
                for tag_id, value in exif_data.items():
                    tag = TAGS.get(tag_id, tag_id)
                    exif[tag] = str(value)

                date_str = exif.get("DateTimeOriginal") or exif.get("DateTime")
                if not date_str:
                    skipped.append({"file": fname, "reason": "No date in EXIF"})
                    continue

                # Parse date: "2024:06:15 14:30:52"
                date_obj = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")

                # Format new name
                if date_format == "YYYYMMDD_HHMMSS":
                    date_part = date_obj.strftime("%Y%m%d_%H%M%S")
                elif date_format == "YYYY-MM-DD":
                    date_part = date_obj.strftime("%Y-%m-%d")
                elif date_format == "YYYYMMDD":
                    date_part = date_obj.strftime("%Y%m%d")
                else:
                    date_part = date_obj.strftime(date_format)

                new_name = f"{prefix}{date_part}{ext}"
                new_path = os.path.join(dir_path, new_name)

                # Handle duplicates
                counter = 1
                while os.path.exists(new_path):
                    new_name = f"{prefix}{date_part}_{counter}{ext}"
                    new_path = os.path.join(dir_path, new_name)
                    counter += 1

                renames.append(
                    {
                        "old": fname,
                        "new": new_name,
                        "date": date_str,
                    }
                )

                # Rename if not dry run
                if not dry_run:
                    os.rename(fpath, new_path)

            except Exception as e:
                skipped.append({"file": fname, "reason": str(e)})

        return ToolResult(
            success=True,
            data={
                "renames": renames,
                "renamed_count": len(renames),
                "skipped": skipped,
                "skipped_count": len(skipped),
                "dry_run": dry_run,
            },
            message=f"{'Would rename' if dry_run else 'Renamed'} {len(renames)} file(s)",
        )


ALL_EXIF_TOOLS = [
    ExtractEXIFTool(),
    BatchRenameByEXIFTool(),
]
