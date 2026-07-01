# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-06-27

### 🎉 Major Feature: Multi-Step Reasoning & Intelligent Path Resolution

#### Added
- **Automatic file path resolution**: Agent now searches for files when exact paths aren't provided
- **Multi-step result passing**: Steps can consume outputs from previous steps using `{{step_N}}` placeholders
- **Smart result extraction**: `result_key` with dot notation support (e.g., `"results.0.path"`)
- **Dependency tracking**: `depends_on` array ensures correct execution order
- **Automatic fallback logic**: Intelligent extraction when `result_key` is not specified

#### Enhanced
- **Planner** (`backend/agent/planner.py`):
  - Added Rule #7: Mandatory file search before operations when path is missing
  - Documented multi-step result passing syntax
  - Added comprehensive examples for `result_key` and placeholder usage

- **Executor** (`backend/agent/executor.py`):
  - Implemented `step_outputs` storage for result chaining
  - Added placeholder replacement logic for `{{step_N}}` syntax
  - Added nested result extraction with dot notation support
  - Enhanced error handling for missing dependencies

#### Documentation
- Added `MULTI_STEP_REASONING.md` - Complete technical documentation
- Added `FIX_SUMMARY.md` - Problem, solution, and testing summary
- Added `docs/MULTI_STEP_FLOW.md` - Visual flow diagrams and examples
- Updated `README.md` - Added multi-step reasoning section with examples

#### Fixed
- **Issue**: Agent failed when user didn't provide exact file paths
  - **Example**: "Rename Bodyweight Progression .pdf" → Error: Path not found
  - **Solution**: Agent now automatically searches for file first, then operates on found path

#### Testing
- Added `tests/test_multi_step.py` - Unit tests for result extraction logic
- Verified extraction logic with dot notation
- Verified compilation of enhanced planner and executor

### Example Workflows Now Supported

```
✅ "Rename myfile.txt to new_name.txt"
   → Search → Rename

✅ "Move all screenshots from last week into Images"
   → Search → Filter by date → Move

✅ "Delete installers older than 6 months"
   → Search by extension → Filter by date → Delete

✅ "Organize my Downloads folder"
   → Scan → Categorize → Create folders → Move files
```

### Technical Details

**Planner Changes:**
- New rule enforces search-before-operate pattern
- Enhanced prompt includes result passing documentation
- Supports `result_key` for extracting specific data
- Supports `{{step_N}}` placeholders in args

**Executor Changes:**
- `step_outputs[index]` stores each step's result
- Placeholder `{{step_N}}` replaced with extracted values
- `result_key` supports dot notation: `"results.0.path"`
- Automatic fallback extraction for common patterns

**Files Modified:**
- `backend/agent/planner.py` (+25 lines)
- `backend/agent/executor.py` (+35 lines)

**Files Added:**
- `MULTI_STEP_REASONING.md` (+250 lines)
- `FIX_SUMMARY.md` (+100 lines)
- `docs/MULTI_STEP_FLOW.md` (+200 lines)
- `tests/test_multi_step.py` (+150 lines)
- `CHANGELOG.md` (this file)

### Backward Compatibility
✅ All changes are backward compatible. Existing plans without `result_key` or placeholders continue to work normally.

---

## [Previous] - Before 2026-06-27

### Features
- Basic natural language to plan conversion
- 68 tools across 10 categories
- Document understanding (summarize, explain, extract tables, compare, find similar)
- Image understanding (OCR, describe, find similar, search by description)
- Security features (permissions, sensitive file detection, encrypt/decrypt, secure delete, audit log)
- Git integration (status, add, commit, diff, log, branch, checkout, push, pull)
- Terminal integration (execute commands, view history, manage processes)
- Photo management (EXIF extraction, batch rename by date)
- Advanced search (fuzzy, semantic, content, documents, code)
- Batch operations (move, delete, rename)
- Memory system for context retention
- Permission system with policy engine
- SQLite audit logging
- WebSocket real-time updates
- Voice input support
- Session-based permission modes
