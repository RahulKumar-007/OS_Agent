# FileAgent AI Features Guide

This guide covers the new AI-powered document and image understanding features.

---

## 📄 Document Understanding

### Summarize Documents

Generate concise AI summaries of any document.

**Supported formats:** PDF, DOCX, XLSX, PPTX, images (OCR), text files

**Example commands:**
- "Summarize the quarterly_report.pdf"
- "Give me a short summary of meeting_notes.docx"
- "Provide a detailed summary of the research paper"

**Parameters:**
- `path`: Document file path (required)
- `max_pages`: Maximum pages to extract (default: 20)
- `summary_length`: 'short' (2-3 sentences), 'medium' (1 paragraph), 'long' (multiple paragraphs)

**Example API usage:**
```json
{
  "tool": "summarize_document",
  "args": {
    "path": "/home/user/Documents/report.pdf",
    "summary_length": "medium"
  }
}
```

---

### Explain Documents

Get detailed AI explanations of document content, purpose, and key concepts.

**Example commands:**
- "Explain what this contract is about"
- "Help me understand this technical document"
- "Explain the methodology in this research paper"

**Parameters:**
- `path`: Document file path (required)
- `max_pages`: Maximum pages to extract (default: 20)
- `focus`: Specific aspect to focus on (optional)

**Example API usage:**
```json
{
  "tool": "explain_document",
  "args": {
    "path": "/home/user/Documents/technical_spec.pdf",
    "focus": "technical details"
  }
}
```

---

### Extract Tables

Extract and structure tables from documents.

**Supported formats:** PDF, DOCX, XLSX, PPTX

**Output formats:** Markdown, JSON, CSV

**Example commands:**
- "Extract all tables from the spreadsheet"
- "Get tables from the PDF in CSV format"
- "Find tables in the document as JSON"

**Parameters:**
- `path`: Document file path (required)
- `format`: 'markdown', 'json', or 'csv' (default: 'markdown')

**Example API usage:**
```json
{
  "tool": "extract_tables",
  "args": {
    "path": "/home/user/Documents/data.pdf",
    "format": "json"
  }
}
```

---

### Compare Documents

Compare two documents to identify similarities and differences.

**Comparison types:**
- **summary**: High-level similarities and differences
- **detailed**: Comprehensive analysis of all aspects
- **content**: Line-by-line content comparison

**Example commands:**
- "Compare contract_v1.pdf and contract_v2.pdf"
- "What changed between the old and new reports?"
- "Find differences in these two documents"

**Parameters:**
- `path1`: First document path (required)
- `path2`: Second document path (required)
- `comparison_type`: 'summary', 'detailed', or 'content' (default: 'summary')

**Example API usage:**
```json
{
  "tool": "compare_documents",
  "args": {
    "path1": "/home/user/Documents/old_version.docx",
    "path2": "/home/user/Documents/new_version.docx",
    "comparison_type": "detailed"
  }
}
```

---

### Find Similar Documents

Find documents similar to a reference document using AI content analysis.

**Example commands:**
- "Find documents similar to this research paper"
- "What other invoices are like this one?"
- "Show me similar contracts"

**Parameters:**
- `reference_path`: Reference document path (required)
- `search_directory`: Directory to search (required)
- `top_n`: Number of results (default: 5)
- `recursive`: Search subdirectories (default: true)

**Example API usage:**
```json
{
  "tool": "find_similar_documents",
  "args": {
    "reference_path": "/home/user/Documents/template.pdf",
    "search_directory": "/home/user/Documents",
    "top_n": 10
  }
}
```

---

## 🖼️ Image Understanding

### Describe Images

Generate AI descriptions of images (currently provides metadata + OCR, full vision requires vision-capable LLM).

**Supported formats:** PNG, JPG, JPEG, TIFF, BMP, WebP, GIF

**Detail levels:**
- **brief**: 1-2 sentence description
- **detailed**: Full description with objects, colors, composition
- **analytical**: Technical analysis (lighting, perspective, etc.)

**Example commands:**
- "Describe this image"
- "What's in this photo?"
- "Analyze the composition of this image"

**Parameters:**
- `path`: Image file path (required)
- `detail_level`: 'brief', 'detailed', or 'analytical' (default: 'detailed')
- `focus`: Specific aspect to focus on (optional)

**Example API usage:**
```json
{
  "tool": "describe_image",
  "args": {
    "path": "/home/user/Pictures/photo.jpg",
    "detail_level": "detailed",
    "focus": "people"
  }
}
```

---

### OCR Image

Extract text from images using Optical Character Recognition.

**Requires:** `tesseract-ocr` installed on system

**Example commands:**
- "Extract text from this screenshot"
- "OCR this scanned document"
- "Read the text in this image"

**Parameters:**
- `path`: Image file path (required)
- `language`: OCR language code (default: 'eng')
- `preprocessing`: 'none', 'enhance', 'denoise' (default: 'none')

**Supported languages:** eng, fra, spa, deu, chi_sim, chi_tra, jpn, rus, ara, hin, and more

**Example API usage:**
```json
{
  "tool": "ocr_image",
  "args": {
    "path": "/home/user/Pictures/screenshot.png",
    "language": "eng",
    "preprocessing": "enhance"
  }
}
```

---

### Find Similar Images

Find visually similar images using perceptual hashing.

**Use cases:**
- Find near-duplicate images
- Locate variations of the same photo
- Identify similar screenshots

**Example commands:**
- "Find images similar to this photo"
- "Show me duplicate images"
- "Find variations of this screenshot"

**Parameters:**
- `reference_path`: Reference image path (required)
- `search_directory`: Directory to search (required)
- `similarity_threshold`: 0.0-1.0, higher = more similar (default: 0.85)
- `recursive`: Search subdirectories (default: true)
- `top_n`: Number of results (default: 10)

**Example API usage:**
```json
{
  "tool": "find_similar_images",
  "args": {
    "reference_path": "/home/user/Pictures/photo1.jpg",
    "search_directory": "/home/user/Pictures",
    "similarity_threshold": 0.9,
    "top_n": 5
  }
}
```

---

### Search Images by Description

Search for images matching a natural language description using OCR and filename analysis.

**Example commands:**
- "Find photos of beaches"
- "Show me screenshots with error messages"
- "Find images containing the word 'invoice'"

**Parameters:**
- `description`: Natural language description (required)
- `search_directory`: Directory to search (required)
- `recursive`: Search subdirectories (default: true)
- `max_results`: Maximum results (default: 20)

**Example API usage:**
```json
{
  "tool": "search_images_by_description",
  "args": {
    "description": "screenshots with error messages",
    "search_directory": "/home/user/Pictures",
    "max_results": 10
  }
}
```

---

## 🔧 Installation Requirements

### Required Python Packages

Already included in `requirements.txt`:
- `python-docx` - Word document processing
- `openpyxl` - Excel file processing
- `python-pptx` - PowerPoint processing
- `pypdf` - PDF text extraction
- `pdfminer.six` - Advanced PDF extraction
- `pytesseract` - OCR wrapper
- `Pillow` - Image processing

### System Dependencies

**For PDF extraction (optional but recommended):**
```bash
sudo apt-get install poppler-utils  # For pdftotext
```

**For OCR (required for image text extraction):**
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-eng
# Additional languages:
sudo apt-get install tesseract-ocr-fra tesseract-ocr-spa tesseract-ocr-deu
```

---

## 💡 Tips and Best Practices

### Document Understanding

1. **Summary length**: Use 'short' for quick overviews, 'long' for comprehensive analysis
2. **Max pages**: Limit pages for faster processing on large PDFs
3. **Focus parameter**: Guide the explanation toward specific aspects you care about
4. **Similar documents**: Works best with documents that share clear themes or topics

### Image Understanding

1. **OCR preprocessing**:
   - Use 'enhance' for low-contrast images
   - Use 'denoise' for noisy/grainy scans
   - Standard images usually work best with 'none'

2. **Similarity threshold**:
   - 0.95-1.0: Near-identical images
   - 0.85-0.95: Very similar (default)
   - 0.70-0.85: Somewhat similar
   - Below 0.70: May produce false positives

3. **Image search**: Works best when images contain visible text or have descriptive filenames

### Performance

- Large PDFs: Use `max_pages` to limit extraction time
- Batch operations: Process similar documents in parallel when possible
- OCR: Can be slow on high-resolution images; consider resizing very large images first

---

## 🐛 Troubleshooting

### "Tesseract OCR not available"
Install tesseract: `sudo apt-get install tesseract-ocr`

### "PIL/Pillow not installed"
Install Pillow: `pip install Pillow`

### "No text content found"
- For PDFs: The PDF might be scanned images (try OCR on extracted images)
- For images: Try different preprocessing options
- For Office docs: File might be corrupted

### "LLM client not configured"
Ensure your LLM server is running and configured in `config.yaml`

### Low OCR accuracy
- Try different preprocessing options ('enhance' or 'denoise')
- Ensure the correct language is specified
- Check image quality and resolution

---

## 🚀 Future Enhancements

Coming soon:
- Vision-capable LLM integration (LLaVA, GPT-4V) for full image understanding
- Object detection with YOLO/Faster R-CNN models
- Document question-answering
- Multi-document summarization
- Image captioning and tagging
