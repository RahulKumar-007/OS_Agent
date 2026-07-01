"""
Document Understanding Tools.
LLM-powered document analysis: summarize, explain, extract tables, compare, find similar.
"""

import os
import re
from typing import Dict, List, Optional

from tools.base import Tool, ToolResult
from tools.extraction_tools import extract_text_from_file


class SummarizeDocumentTool(Tool):
    name = "summarize_document"
    description = (
        "Generate a concise summary of a document using AI. "
        "Works with PDF, DOCX, XLSX, PPTX, images (OCR), and text files."
    )
    parameters_schema = {
        "path": "Absolute path to the document file",
        "max_pages": "(optional) Max pages to extract. Default 20.",
        "summary_length": "(optional) 'short' (2-3 sentences), 'medium' (1 paragraph), 'long' (multiple paragraphs). Default 'medium'.",
    }

    def __init__(self):
        super().__init__()
        self.llm_client = None  # Injected at startup

    async def execute(self, args: Dict) -> ToolResult:
        if not self.llm_client:
            return ToolResult(success=False, message="LLM client not configured")

        path = os.path.expanduser(args.get("path", ""))
        max_pages = int(args.get("max_pages", 20))
        summary_length = args.get("summary_length", "medium").lower()

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"File does not exist: {path}")
        if os.path.isdir(path):
            return ToolResult(success=False, message=f"Not a file: {path}")

        # Extract text
        extraction = extract_text_from_file(path, max_pages)
        if extraction.get("error") and not extraction.get("text"):
            return ToolResult(
                success=False, message=f"Text extraction failed: {extraction['error']}"
            )

        text = extraction.get("text", "")
        if not text.strip():
            return ToolResult(
                success=False, message="No text content found in document"
            )

        # Truncate if too long (keep first ~8000 chars for LLM context)
        if len(text) > 8000:
            text = text[:8000] + "\n\n[... document truncated for summarization ...]"

        # Build prompt based on length
        length_instructions = {
            "short": "Provide a very concise 2-3 sentence summary.",
            "medium": "Provide a comprehensive paragraph summarizing the main points.",
            "long": "Provide a detailed summary with multiple paragraphs covering key topics, findings, and conclusions.",
        }
        instruction = length_instructions.get(
            summary_length, length_instructions["medium"]
        )

        prompt = f"""You are a document analysis assistant. Summarize the following document.

{instruction}

Document ({os.path.basename(path)}):
---
{text}
---

Summary:"""

        # Call LLM
        try:
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024,
            )

            if response.get("error"):
                return ToolResult(
                    success=False, message=f"LLM error: {response['error']}"
                )

            summary = response.get("content", "").strip()

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "name": os.path.basename(path),
                    "summary": summary,
                    "summary_length": summary_length,
                    "document_length": len(extraction.get("text", "")),
                    "method": extraction.get("method"),
                },
                message=f"Generated {summary_length} summary of {os.path.basename(path)}",
                files_affected=[path],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Summarization failed: {str(e)}")


class ExplainDocumentTool(Tool):
    name = "explain_document"
    description = (
        "Get an AI explanation of a document's content, purpose, and key concepts. "
        "More detailed than a summary — includes context, terminology, and analysis."
    )
    parameters_schema = {
        "path": "Absolute path to the document file",
        "max_pages": "(optional) Max pages to extract. Default 20.",
        "focus": "(optional) Specific aspect to focus explanation on (e.g., 'technical details', 'business implications', 'methodology')",
    }

    def __init__(self):
        super().__init__()
        self.llm_client = None

    async def execute(self, args: Dict) -> ToolResult:
        if not self.llm_client:
            return ToolResult(success=False, message="LLM client not configured")

        path = os.path.expanduser(args.get("path", ""))
        max_pages = int(args.get("max_pages", 20))
        focus = args.get("focus", "")

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"File does not exist: {path}")

        # Extract text
        extraction = extract_text_from_file(path, max_pages)
        if extraction.get("error") and not extraction.get("text"):
            return ToolResult(
                success=False, message=f"Text extraction failed: {extraction['error']}"
            )

        text = extraction.get("text", "")
        if not text.strip():
            return ToolResult(success=False, message="No text content found")

        # Truncate if needed
        if len(text) > 8000:
            text = text[:8000] + "\n\n[... document truncated ...]"

        focus_instruction = f"\nFocus your explanation on: {focus}" if focus else ""

        prompt = f"""You are a document analysis expert. Explain the following document in detail.

Your explanation should include:
1. What this document is and its purpose
2. Key concepts and terminology used
3. Main topics covered
4. Target audience and context
5. Important takeaways{focus_instruction}

Document ({os.path.basename(path)}):
---
{text}
---

Detailed Explanation:"""

        try:
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=2048,
            )

            if response.get("error"):
                return ToolResult(
                    success=False, message=f"LLM error: {response['error']}"
                )

            explanation = response.get("content", "").strip()

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "name": os.path.basename(path),
                    "explanation": explanation,
                    "focus": focus,
                    "document_length": len(extraction.get("text", "")),
                },
                message=f"Generated explanation for {os.path.basename(path)}",
                files_affected=[path],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Explanation failed: {str(e)}")


class ExtractTablesTool(Tool):
    name = "extract_tables"
    description = (
        "Extract and structure tables from documents (PDF, DOCX, XLSX, PPTX). "
        "Returns tables in a structured format with AI-powered cleanup and formatting."
    )
    parameters_schema = {
        "path": "Absolute path to the document file",
        "format": "(optional) Output format: 'markdown', 'json', 'csv'. Default 'markdown'.",
    }

    def __init__(self):
        super().__init__()
        self.llm_client = None

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        output_format = args.get("format", "markdown").lower()

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"File does not exist: {path}")

        # Extract text
        extraction = extract_text_from_file(path, max_pages=50)
        text = extraction.get("text", "")

        if not text.strip():
            return ToolResult(success=False, message="No text content found")

        # Look for table-like patterns in text
        tables_found = []

        # Pattern 1: Lines with | separators (markdown-style or extracted tables)
        lines = text.split("\n")
        current_table = []
        in_table = False

        for line in lines:
            if "|" in line and line.count("|") >= 2:
                current_table.append(line.strip())
                in_table = True
            elif in_table and current_table:
                # End of table
                if len(current_table) >= 2:  # At least header + 1 row
                    tables_found.append("\n".join(current_table))
                current_table = []
                in_table = False

        # Catch last table
        if current_table and len(current_table) >= 2:
            tables_found.append("\n".join(current_table))

        if not tables_found:
            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "name": os.path.basename(path),
                    "tables": [],
                    "count": 0,
                },
                message=f"No tables found in {os.path.basename(path)}",
                files_affected=[path],
            )

        # Format tables based on requested format
        formatted_tables = []
        for i, table_text in enumerate(tables_found, 1):
            if output_format == "markdown":
                formatted_tables.append(
                    {
                        "index": i,
                        "format": "markdown",
                        "content": table_text,
                    }
                )
            elif output_format == "json":
                # Parse markdown table to JSON
                rows = [r.strip() for r in table_text.split("\n") if r.strip()]
                if rows:
                    headers = [h.strip() for h in rows[0].split("|") if h.strip()]
                    data_rows = []
                    for row in rows[1:]:
                        if "---" in row or "===" in row:  # Skip separator rows
                            continue
                        cells = [c.strip() for c in row.split("|") if c.strip()]
                        if cells and len(cells) == len(headers):
                            data_rows.append(dict(zip(headers, cells)))
                    formatted_tables.append(
                        {
                            "index": i,
                            "format": "json",
                            "headers": headers,
                            "rows": data_rows,
                        }
                    )
            elif output_format == "csv":
                # Convert to CSV format
                rows = [r.strip() for r in table_text.split("\n") if r.strip()]
                csv_lines = []
                for row in rows:
                    if "---" in row or "===" in row:
                        continue
                    cells = [c.strip() for c in row.split("|") if c.strip()]
                    if cells:
                        csv_lines.append(",".join(f'"{c}"' for c in cells))
                formatted_tables.append(
                    {
                        "index": i,
                        "format": "csv",
                        "content": "\n".join(csv_lines),
                    }
                )

        return ToolResult(
            success=True,
            data={
                "path": path,
                "name": os.path.basename(path),
                "tables": formatted_tables,
                "count": len(formatted_tables),
                "format": output_format,
            },
            message=f"Extracted {len(formatted_tables)} table(s) from {os.path.basename(path)}",
            files_affected=[path],
        )


class CompareDocumentsTool(Tool):
    name = "compare_documents"
    description = (
        "Compare two documents and identify similarities, differences, and changes. "
        "Useful for comparing versions, finding discrepancies, or understanding relationships."
    )
    parameters_schema = {
        "path1": "Absolute path to first document",
        "path2": "Absolute path to second document",
        "comparison_type": "(optional) 'content' (text comparison), 'summary' (high-level differences), 'detailed' (line-by-line). Default 'summary'.",
    }

    def __init__(self):
        super().__init__()
        self.llm_client = None

    async def execute(self, args: Dict) -> ToolResult:
        if not self.llm_client:
            return ToolResult(success=False, message="LLM client not configured")

        path1 = os.path.expanduser(args.get("path1", ""))
        path2 = os.path.expanduser(args.get("path2", ""))
        comparison_type = args.get("comparison_type", "summary").lower()

        if not os.path.exists(path1):
            return ToolResult(success=False, message=f"File does not exist: {path1}")
        if not os.path.exists(path2):
            return ToolResult(success=False, message=f"File does not exist: {path2}")

        # Extract text from both documents
        extraction1 = extract_text_from_file(path1, max_pages=20)
        extraction2 = extract_text_from_file(path2, max_pages=20)

        text1 = extraction1.get("text", "")[:4000]
        text2 = extraction2.get("text", "")[:4000]

        if not text1.strip() or not text2.strip():
            return ToolResult(
                success=False, message="One or both documents have no text content"
            )

        # Build comparison prompt
        if comparison_type == "summary":
            prompt = f"""Compare these two documents and provide a high-level summary of:
1. Main similarities
2. Key differences
3. Which aspects each document emphasizes

Document 1 ({os.path.basename(path1)}):
---
{text1}
---

Document 2 ({os.path.basename(path2)}):
---
{text2}
---

Comparison:"""
        elif comparison_type == "detailed":
            prompt = f"""Provide a detailed comparison of these documents:
1. Content similarities (topics, facts, data)
2. Content differences (unique to each document)
3. Structural differences (organization, format)
4. Tone and style differences
5. Recommendations or conclusions

Document 1 ({os.path.basename(path1)}):
---
{text1}
---

Document 2 ({os.path.basename(path2)}):
---
{text2}
---

Detailed Analysis:"""
        else:  # content
            prompt = f"""Compare the actual content of these documents. Identify:
1. Identical or near-identical sections
2. Modified sections (what changed)
3. Content only in Document 1
4. Content only in Document 2

Document 1 ({os.path.basename(path1)}):
---
{text1}
---

Document 2 ({os.path.basename(path2)}):
---
{text2}
---

Content Comparison:"""

        try:
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2048,
            )

            if response.get("error"):
                return ToolResult(
                    success=False, message=f"LLM error: {response['error']}"
                )

            comparison = response.get("content", "").strip()

            return ToolResult(
                success=True,
                data={
                    "document1": {"path": path1, "name": os.path.basename(path1)},
                    "document2": {"path": path2, "name": os.path.basename(path2)},
                    "comparison": comparison,
                    "comparison_type": comparison_type,
                },
                message=f"Compared {os.path.basename(path1)} and {os.path.basename(path2)}",
                files_affected=[path1, path2],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Comparison failed: {str(e)}")


class FindSimilarDocumentsTool(Tool):
    name = "find_similar_documents"
    description = (
        "Find documents in a directory that are similar to a given document. "
        "Uses content analysis to identify thematically or structurally similar files."
    )
    parameters_schema = {
        "reference_path": "Absolute path to reference document",
        "search_directory": "Directory to search for similar documents",
        "top_n": "(optional) Number of most similar documents to return. Default 5.",
        "recursive": "(optional) Search recursively. Default true.",
    }

    def __init__(self):
        super().__init__()
        self.llm_client = None

    async def execute(self, args: Dict) -> ToolResult:
        if not self.llm_client:
            return ToolResult(success=False, message="LLM client not configured")

        reference_path = os.path.expanduser(args.get("reference_path", ""))
        search_dir = os.path.expanduser(args.get("search_directory", ""))
        top_n = int(args.get("top_n", 5))
        recursive = args.get("recursive", True)

        if not os.path.exists(reference_path):
            return ToolResult(
                success=False,
                message=f"Reference file does not exist: {reference_path}",
            )
        if not os.path.exists(search_dir):
            return ToolResult(
                success=False, message=f"Search directory does not exist: {search_dir}"
            )

        # Extract reference document
        ref_extraction = extract_text_from_file(reference_path, max_pages=10)
        ref_text = ref_extraction.get("text", "")[
            :2000
        ]  # Keep it shorter for multiple comparisons

        if not ref_text.strip():
            return ToolResult(
                success=False, message="Reference document has no text content"
            )

        # Find candidate documents
        from tools.extraction_tools import (
            BINARY_DOCUMENT_EXTENSIONS,
            IMAGE_EXTENSIONS,
            SUPPORTED_EXTENSIONS,
        )

        ALL_EXTRACTABLE = (
            SUPPORTED_EXTENSIONS | BINARY_DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS
        )

        candidates = []
        try:
            if recursive:
                for root, dirs, files in os.walk(search_dir):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        if fpath == reference_path:
                            continue  # Skip reference file
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in ALL_EXTRACTABLE:
                            candidates.append(fpath)
                            if len(candidates) >= 20:  # Limit for performance
                                break
                    if len(candidates) >= 20:
                        break
            else:
                for fname in os.listdir(search_dir):
                    fpath = os.path.join(search_dir, fname)
                    if os.path.isfile(fpath) and fpath != reference_path:
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in ALL_EXTRACTABLE:
                            candidates.append(fpath)
                            if len(candidates) >= 20:
                                break
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {search_dir}")

        if not candidates:
            return ToolResult(
                success=True,
                data={
                    "reference": reference_path,
                    "similar_documents": [],
                    "search_directory": search_dir,
                },
                message="No candidate documents found",
            )

        # Extract text from candidates and use LLM to rank similarity
        candidate_texts = []
        for cpath in candidates[:10]:  # Further limit for LLM processing
            extraction = extract_text_from_file(cpath, max_pages=5)
            text = extraction.get("text", "")[:1000]
            if text.strip():
                candidate_texts.append(
                    {
                        "path": cpath,
                        "name": os.path.basename(cpath),
                        "text": text,
                    }
                )

        # Use LLM to rank similarity
        candidates_summary = "\n\n".join(
            [
                f"[{i}] {c['name']}:\n{c['text'][:300]}..."
                for i, c in enumerate(candidate_texts, 1)
            ]
        )

        prompt = f"""You are comparing documents for similarity. Given a reference document and several candidate documents, rank the candidates by similarity to the reference.

Consider: topic overlap, content type, purpose, terminology, and structure.

Reference Document ({os.path.basename(reference_path)}):
---
{ref_text}
---

Candidate Documents:
{candidates_summary}

Provide the top {min(top_n, len(candidate_texts))} most similar documents. For each, explain why it's similar.

Respond in JSON format:
{{
  "similar_documents": [
    {{"index": 1, "name": "filename", "similarity_reason": "explanation"}},
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
            if not parsed or "similar_documents" not in parsed:
                return ToolResult(
                    success=False, message="Failed to parse similarity rankings"
                )

            # Map indices back to paths
            results = []
            for item in parsed["similar_documents"][:top_n]:
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(candidate_texts):
                    results.append(
                        {
                            "path": candidate_texts[idx]["path"],
                            "name": candidate_texts[idx]["name"],
                            "similarity_reason": item.get(
                                "similarity_reason", "Similar content"
                            ),
                        }
                    )

            return ToolResult(
                success=True,
                data={
                    "reference": {
                        "path": reference_path,
                        "name": os.path.basename(reference_path),
                    },
                    "similar_documents": results,
                    "search_directory": search_dir,
                    "total_candidates_checked": len(candidate_texts),
                },
                message=f"Found {len(results)} similar document(s) to {os.path.basename(reference_path)}",
                files_affected=[reference_path],
            )
        except Exception as e:
            return ToolResult(
                success=False, message=f"Similarity search failed: {str(e)}"
            )


class SummarizeFolderTool(Tool):
    name = "summarize_folder"
    description = (
        "Generate AI summary of all documents in a folder. "
        "Perfect for 'summarize this folder' requests."
    )
    parameters_schema = {
        "path": "Directory path to summarize",
        "max_files": "(optional) Max files to process. Default 20.",
        "recursive": "(optional) Include subdirectories. Default false.",
    }

    def __init__(self):
        super().__init__()
        self.llm_client = None

    async def execute(self, args: Dict) -> ToolResult:
        if not self.llm_client:
            return ToolResult(success=False, message="LLM client not configured")

        path = os.path.expanduser(args.get("path", ""))
        max_files = int(args.get("max_files", 20))
        recursive = args.get("recursive", False)

        if not os.path.exists(path) or not os.path.isdir(path):
            return ToolResult(success=False, message=f"Invalid directory: {path}")

        # Find documents
        from tools.extraction_tools import (
            BINARY_DOCUMENT_EXTENSIONS,
            SUPPORTED_EXTENSIONS,
        )

        target_exts = SUPPORTED_EXTENSIONS | BINARY_DOCUMENT_EXTENSIONS

        files = []
        try:
            if recursive:
                for root, dirs, fnames in os.walk(path):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    for fname in fnames:
                        if len(files) >= max_files:
                            break
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in target_exts:
                            files.append(os.path.join(root, fname))
            else:
                for fname in os.listdir(path):
                    if len(files) >= max_files:
                        break
                    fpath = os.path.join(path, fname)
                    if os.path.isfile(fpath):
                        ext = os.path.splitext(fname)[1].lower()
                        if ext in target_exts:
                            files.append(fpath)
        except PermissionError:
            return ToolResult(success=False, message=f"Permission denied: {path}")

        if not files:
            return ToolResult(
                success=True,
                data={"summary": "No documents found"},
                message="Empty folder",
            )

        # Extract text from each file
        contents = []
        for fpath in files[:max_files]:
            extraction = extract_text_from_file(fpath, max_pages=5)
            text = extraction.get("text", "")[:1000]  # First 1000 chars per file
            if text.strip():
                contents.append(f"File: {os.path.basename(fpath)}\n{text}")

        if not contents:
            return ToolResult(
                success=True,
                data={"summary": "No readable content"},
                message="No content",
            )

        # Combine for LLM
        combined = "\n\n---\n\n".join(contents)
        if len(combined) > 6000:
            combined = combined[:6000] + "\n\n[... truncated ...]"

        prompt = f"""Summarize the contents of this folder in 2-3 paragraphs.

Folder: {os.path.basename(path)}
Files: {len(files)}

{combined}

Summary:"""

        try:
            response = await self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=512,
            )

            if response.get("error"):
                return ToolResult(
                    success=False, message=f"LLM error: {response['error']}"
                )

            summary = response.get("content", "").strip()

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "files_processed": len(files),
                    "summary": summary,
                },
                message=f"Summarized {len(files)} file(s)",
                files_affected=[path],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Folder summary failed: {str(e)}")


ALL_DOCUMENT_UNDERSTANDING_TOOLS = [
    SummarizeDocumentTool(),
    ExplainDocumentTool(),
    ExtractTablesTool(),
    CompareDocumentsTool(),
    FindSimilarDocumentsTool(),
    SummarizeFolderTool(),
]
