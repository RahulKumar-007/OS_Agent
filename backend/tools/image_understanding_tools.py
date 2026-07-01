"""
Image Understanding Tools.
AI-powered image analysis: describe, OCR, object detection, similarity search.
"""

import base64
import json
import os
from typing import Dict, List

from tools.base import Tool, ToolResult

# Check for image processing libraries
HAS_PIL = False
HAS_TESSERACT = False

try:
    import PIL
    from PIL import Image

    HAS_PIL = True
except ImportError:
    pass

try:
    import pytesseract

    HAS_TESSERACT = True
except ImportError:
    pass

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp", ".gif"}


def image_to_base64(image_path: str, max_size: int = 800) -> str:
    """Convert image to base64, optionally resizing for LLM efficiency."""
    if not HAS_PIL:
        raise ImportError("PIL/Pillow not installed")

    img = Image.open(image_path)

    # Resize if too large
    if max(img.size) > max_size:
        ratio = max_size / max(img.size)
        new_size = tuple(int(dim * ratio) for dim in img.size)
        img = img.resize(new_size, Image.Resampling.LANCZOS)

    # Convert to RGB if needed
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    # Save to bytes
    import io

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return base64.b64encode(buffer.read()).decode("utf-8")


class DescribeImageTool(Tool):
    name = "describe_image"
    description = (
        "Generate a detailed AI description of an image. "
        "Identifies objects, scenes, activities, colors, composition, and context."
    )
    parameters_schema = {
        "path": "Absolute path to the image file",
        "detail_level": "(optional) 'brief' (1-2 sentences), 'detailed' (full description), 'analytical' (technical analysis). Default 'detailed'.",
        "focus": "(optional) Specific aspect to focus on (e.g., 'people', 'text', 'objects', 'colors', 'composition')",
    }

    def __init__(self):
        super().__init__()
        self.llm_client = None

    async def execute(self, args: Dict) -> ToolResult:
        if not self.llm_client:
            return ToolResult(success=False, message="LLM client not configured")
        if not HAS_PIL:
            return ToolResult(
                success=False,
                message="PIL/Pillow not installed. Install: pip install Pillow",
            )

        path = os.path.expanduser(args.get("path", ""))
        detail_level = args.get("detail_level", "detailed").lower()
        focus = args.get("focus", "")

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"File does not exist: {path}")

        ext = os.path.splitext(path)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            return ToolResult(
                success=False, message=f"Not a supported image format: {ext}"
            )

        # Get image metadata
        try:
            img = Image.open(path)
            width, height = img.size
            mode = img.mode
            format_name = img.format
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to open image: {str(e)}")

        # Build prompt based on detail level
        detail_instructions = {
            "brief": "Provide a concise 1-2 sentence description of what you see.",
            "detailed": "Provide a detailed description including: main subjects, background, colors, mood, composition, and any notable details.",
            "analytical": "Provide a technical analysis including: composition, lighting, color palette, perspective, visual hierarchy, and artistic elements.",
        }
        instruction = detail_instructions.get(
            detail_level, detail_instructions["detailed"]
        )

        focus_text = f"\n\nFocus specifically on: {focus}" if focus else ""

        prompt = f"""You are an image analysis expert. Describe this image.

{instruction}{focus_text}

Image details: {width}x{height}px, {mode} mode, {format_name} format.

Provide your description:"""

        # Note: Most local LLMs don't support vision yet, so we'll use text-only description
        # For now, provide a structured response based on what we can detect
        # In the future, this could be enhanced with vision-capable models

        try:
            # Fallback: Use basic image analysis
            description = f"Image file: {os.path.basename(path)}\n"
            description += f"Dimensions: {width}x{height} pixels\n"
            description += f"Format: {format_name}\n"
            description += f"Color mode: {mode}\n"

            # Try to extract text with OCR if available
            if HAS_TESSERACT:
                try:
                    text = pytesseract.image_to_string(img)
                    if text.strip():
                        description += f"\nText detected in image:\n{text.strip()}"
                except:
                    pass

            # Since most local LLMs don't support vision, return structured info
            # This tool is a placeholder for future vision model integration
            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "name": os.path.basename(path),
                    "description": description,
                    "width": width,
                    "height": height,
                    "format": format_name,
                    "mode": mode,
                    "detail_level": detail_level,
                    "note": "Full AI vision description requires a vision-capable LLM (e.g., LLaVA, GPT-4V). Currently providing image metadata and OCR.",
                },
                message=f"Analyzed image: {os.path.basename(path)}",
                files_affected=[path],
            )

        except Exception as e:
            return ToolResult(
                success=False, message=f"Image description failed: {str(e)}"
            )


class OCRImageTool(Tool):
    name = "ocr_image"
    description = (
        "Extract text from an image using OCR (Optical Character Recognition). "
        "Useful for reading text in screenshots, scanned documents, photos of text, etc."
    )
    parameters_schema = {
        "path": "Absolute path to the image file",
        "language": "(optional) OCR language code (e.g., 'eng', 'fra', 'spa'). Default 'eng'.",
        "preprocessing": "(optional) Apply image preprocessing: 'none', 'enhance', 'denoise'. Default 'none'.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        if not HAS_PIL:
            return ToolResult(success=False, message="PIL/Pillow not installed")
        if not HAS_TESSERACT:
            return ToolResult(
                success=False,
                message="Tesseract OCR not installed. Install: sudo apt-get install tesseract-ocr && pip install pytesseract",
            )

        path = os.path.expanduser(args.get("path", ""))
        language = args.get("language", "eng")
        preprocessing = args.get("preprocessing", "none").lower()

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"File does not exist: {path}")

        ext = os.path.splitext(path)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            return ToolResult(
                success=False, message=f"Not a supported image format: {ext}"
            )

        try:
            import pytesseract

            img = Image.open(path)

            # Preprocessing
            if preprocessing == "enhance":
                # Enhance contrast and sharpness
                from PIL import ImageEnhance

                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(2.0)
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(1.5)
            elif preprocessing == "denoise":
                # Convert to grayscale and apply threshold
                img = img.convert("L")
                from PIL import ImageFilter

                img = img.filter(ImageFilter.MedianFilter(size=3))

            # Perform OCR
            text = pytesseract.image_to_string(img, lang=language)

            # Get confidence data
            data = pytesseract.image_to_data(
                img, lang=language, output_type=pytesseract.Output.DICT
            )
            confidences = [c for c in data["conf"] if c != -1]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "name": os.path.basename(path),
                    "text": text.strip(),
                    "text_length": len(text.strip()),
                    "language": language,
                    "preprocessing": preprocessing,
                    "confidence": round(avg_confidence, 2),
                    "word_count": len(text.split()),
                },
                message=f"Extracted {len(text.split())} words from {os.path.basename(path)} (confidence: {avg_confidence:.1f}%)",
                files_affected=[path],
            )

        except Exception as e:
            return ToolResult(success=False, message=f"OCR failed: {str(e)}")


class DetectObjectsTool(Tool):
    name = "detect_objects"
    description = (
        "Detect and identify objects in an image. "
        "Note: Requires a vision-capable LLM or object detection model."
    )
    parameters_schema = {
        "path": "Absolute path to the image file",
        "confidence_threshold": "(optional) Minimum confidence (0.0-1.0) for detection. Default 0.5.",
    }

    def __init__(self):
        super().__init__()
        self.llm_client = None

    async def execute(self, args: Dict) -> ToolResult:
        if not HAS_PIL:
            return ToolResult(success=False, message="PIL/Pillow not installed")

        path = os.path.expanduser(args.get("path", ""))
        confidence_threshold = float(args.get("confidence_threshold", 0.5))

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"File does not exist: {path}")

        ext = os.path.splitext(path)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            return ToolResult(
                success=False, message=f"Not a supported image format: {ext}"
            )

        try:
            img = Image.open(path)
            width, height = img.size

            # Placeholder: Real object detection requires specialized models (YOLO, Faster R-CNN, etc.)
            # or vision-capable LLMs like LLaVA
            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "name": os.path.basename(path),
                    "objects": [],
                    "note": "Object detection requires a vision model (YOLO, Faster R-CNN, LLaVA, etc.). This is a placeholder for future integration.",
                    "image_size": {"width": width, "height": height},
                },
                message=f"Object detection not yet implemented (requires vision model)",
                files_affected=[path],
            )

        except Exception as e:
            return ToolResult(
                success=False, message=f"Object detection failed: {str(e)}"
            )


class FindSimilarImagesTool(Tool):
    name = "find_similar_images"
    description = (
        "Find visually similar images in a directory using perceptual hashing. "
        "Detects near-duplicates and similar images based on visual content."
    )
    parameters_schema = {
        "reference_path": "Absolute path to reference image",
        "search_directory": "Directory to search for similar images",
        "similarity_threshold": "(optional) Similarity threshold 0.0-1.0 (higher = more similar). Default 0.85.",
        "recursive": "(optional) Search recursively. Default true.",
        "top_n": "(optional) Number of most similar images to return. Default 10.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        if not HAS_PIL:
            return ToolResult(success=False, message="PIL/Pillow not installed")

        reference_path = os.path.expanduser(args.get("reference_path", ""))
        search_dir = os.path.expanduser(args.get("search_directory", ""))
        similarity_threshold = float(args.get("similarity_threshold", 0.85))
        recursive = args.get("recursive", True)
        top_n = int(args.get("top_n", 10))

        if not os.path.exists(reference_path):
            return ToolResult(
                success=False,
                message=f"Reference image does not exist: {reference_path}",
            )
        if not os.path.exists(search_dir):
            return ToolResult(
                success=False, message=f"Search directory does not exist: {search_dir}"
            )

        try:
            # Compute perceptual hash of reference image
            ref_img = Image.open(reference_path)
            ref_hash = self._perceptual_hash(ref_img)

            # Find candidate images
            candidates = []
            try:
                if recursive:
                    for root, dirs, files in os.walk(search_dir):
                        for fname in files:
                            fpath = os.path.join(root, fname)
                            if fpath == reference_path:
                                continue
                            ext = os.path.splitext(fname)[1].lower()
                            if ext in IMAGE_EXTENSIONS:
                                candidates.append(fpath)
                else:
                    for fname in os.listdir(search_dir):
                        fpath = os.path.join(search_dir, fname)
                        if os.path.isfile(fpath) and fpath != reference_path:
                            ext = os.path.splitext(fname)[1].lower()
                            if ext in IMAGE_EXTENSIONS:
                                candidates.append(fpath)
            except PermissionError:
                return ToolResult(
                    success=False, message=f"Permission denied: {search_dir}"
                )

            if not candidates:
                return ToolResult(
                    success=True,
                    data={
                        "reference": reference_path,
                        "similar_images": [],
                        "search_directory": search_dir,
                    },
                    message="No candidate images found",
                )

            # Compare each candidate
            similarities = []
            for cpath in candidates:
                try:
                    cimg = Image.open(cpath)
                    chash = self._perceptual_hash(cimg)
                    similarity = self._hash_similarity(ref_hash, chash)

                    if similarity >= similarity_threshold:
                        similarities.append(
                            {
                                "path": cpath,
                                "name": os.path.basename(cpath),
                                "similarity": round(similarity, 3),
                            }
                        )
                except Exception:
                    continue  # Skip problematic images

            # Sort by similarity (highest first)
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            results = similarities[:top_n]

            return ToolResult(
                success=True,
                data={
                    "reference": {
                        "path": reference_path,
                        "name": os.path.basename(reference_path),
                    },
                    "similar_images": results,
                    "search_directory": search_dir,
                    "total_candidates_checked": len(candidates),
                    "threshold": similarity_threshold,
                },
                message=f"Found {len(results)} similar image(s) to {os.path.basename(reference_path)}",
                files_affected=[reference_path],
            )

        except Exception as e:
            return ToolResult(
                success=False, message=f"Image similarity search failed: {str(e)}"
            )

    def _perceptual_hash(self, img: Image.Image, hash_size: int = 8) -> str:
        """Compute perceptual hash (pHash) of an image."""
        # Resize to small size
        img = img.convert("L").resize((hash_size, hash_size), Image.Resampling.LANCZOS)

        # Get pixel values
        pixels = list(img.getdata())

        # Compute average
        avg = sum(pixels) / len(pixels)

        # Create hash based on whether pixel is above/below average
        hash_bits = "".join("1" if p > avg else "0" for p in pixels)

        return hash_bits

    def _hash_similarity(self, hash1: str, hash2: str) -> float:
        """Compute similarity between two hashes (Hamming distance)."""
        if len(hash1) != len(hash2):
            return 0.0

        # Count matching bits
        matches = sum(b1 == b2 for b1, b2 in zip(hash1, hash2))

        return matches / len(hash1)


class SearchImagesByDescriptionTool(Tool):
    name = "search_images_by_description"
    description = (
        "Search for images matching a natural language description. "
        "Uses OCR and filename analysis to find relevant images."
    )
    parameters_schema = {
        "description": "Natural language description of images to find (e.g., 'photos of beaches', 'screenshots with error messages')",
        "search_directory": "Directory to search",
        "recursive": "(optional) Search recursively. Default true.",
        "max_results": "(optional) Maximum number of results. Default 20.",
    }

    def __init__(self):
        super().__init__()
        self.llm_client = None

    async def execute(self, args: Dict) -> ToolResult:
        if not self.llm_client:
            return ToolResult(success=False, message="LLM client not configured")
        if not HAS_PIL:
            return ToolResult(success=False, message="PIL/Pillow not installed")

        description = args.get("description", "")
        search_dir = os.path.expanduser(args.get("search_directory", ""))
        recursive = args.get("recursive", True)
        max_results = int(args.get("max_results", 20))

        if not description:
            return ToolResult(success=False, message="Description is required")
        if not os.path.exists(search_dir):
            return ToolResult(
                success=False, message=f"Search directory does not exist: {search_dir}"
            )

        # Find all images
        image_files = []
        try:
            if recursive:
                for root, dirs, files in os.walk(search_dir):
                    for fname in files:
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in IMAGE_EXTENSIONS:
                            image_files.append(os.path.join(root, fname))
                            if len(image_files) >= 100:  # Limit for performance
                                break
                    if len(image_files) >= 100:
                        break
            else:
                for fname in os.listdir(search_dir):
                    fpath = os.path.join(search_dir, fname)
                    if os.path.isfile(fpath):
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in IMAGE_EXTENSIONS:
                            image_files.append(fpath)
                            if len(image_files) >= 100:
                                break
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {search_dir}")

        if not image_files:
            return ToolResult(
                success=True,
                data={
                    "matches": [],
                    "search_directory": search_dir,
                    "description": description,
                },
                message="No images found in search directory",
            )

        # Extract text from images (if OCR available) and analyze filenames
        candidates = []
        for img_path in image_files[:50]:  # Limit for OCR processing
            metadata = {"path": img_path, "name": os.path.basename(img_path)}

            # Extract text with OCR
            if HAS_TESSERACT:
                try:
                    import pytesseract

                    img = Image.open(img_path)
                    text = pytesseract.image_to_string(img)
                    metadata["ocr_text"] = text.strip()[:500]  # Keep first 500 chars
                except:
                    metadata["ocr_text"] = ""
            else:
                metadata["ocr_text"] = ""

            candidates.append(metadata)

        # Use LLM to rank relevance
        candidates_summary = "\n".join(
            [
                f"[{i}] {c['name']}\nOCR: {c['ocr_text'][:100] if c['ocr_text'] else 'No text detected'}"
                for i, c in enumerate(candidates, 1)
            ]
        )

        prompt = f"""You are searching for images based on a description. Given the description and information about candidate images (filename and OCR text), identify which images match.

Search description: "{description}"

Candidate images:
{candidates_summary}

Return the indices of matching images in order of relevance (most relevant first).

Respond in JSON format:
{{
  "matches": [
    {{"index": 1, "relevance_reason": "explanation"}},
    ...
  ]
}}
"""

        try:
            response = await self.llm_client.generate_json(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )

            if response.get("error"):
                return ToolResult(
                    success=False, message=f"LLM error: {response['error']}"
                )

            parsed = response.get("parsed")
            if not parsed or "matches" not in parsed:
                return ToolResult(
                    success=False, message="Failed to parse search results"
                )

            # Map indices back to paths
            results = []
            for item in parsed["matches"][:max_results]:
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(candidates):
                    results.append(
                        {
                            "path": candidates[idx]["path"],
                            "name": candidates[idx]["name"],
                            "relevance_reason": item.get(
                                "relevance_reason", "Matches description"
                            ),
                        }
                    )

            return ToolResult(
                success=True,
                data={
                    "description": description,
                    "matches": results,
                    "search_directory": search_dir,
                    "total_images_checked": len(candidates),
                },
                message=f"Found {len(results)} image(s) matching '{description}'",
            )

        except Exception as e:
            return ToolResult(success=False, message=f"Image search failed: {str(e)}")


ALL_IMAGE_UNDERSTANDING_TOOLS = [
    DescribeImageTool(),
    OCRImageTool(),
    DetectObjectsTool(),
    FindSimilarImagesTool(),
    SearchImagesByDescriptionTool(),
]
