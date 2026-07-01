# Multi-Step Reasoning & Result Passing

## Problem

When users ask to perform operations on files without providing full paths (e.g., "Rename Bodyweight Progression.pdf"), the agent was trying to operate on files at assumed paths instead of searching for them first.

**Example failure:**
```
User: "Rename the file Bodyweight Progression .pdf to Bodyweight_Progression.pdf"
Agent: Tries to rename ~/Bodyweight Progression .pdf (fails - wrong path)
```

The agent should have:
1. Searched for the file first
2. Used the search result's path in the rename operation

## Solution

Implemented **multi-step result passing** allowing steps to consume outputs from previous steps.

### Changes Made

#### 1. Enhanced Planner Prompt (`planner.py`)
- Added Rule #7: **Mandatory file search before operations when path is unknown**
- Documented `result_key` for extracting specific data from step results
- Added `{{step_N}}` placeholder syntax for referencing previous step outputs
- Supports dot notation for nested extraction: `"results.0.path"`

#### 2. Enhanced Executor (`executor.py`)
- **Result Storage**: Each step's output is stored in `step_outputs[step_index]`
- **Placeholder Replacement**: `{{step_0}}`, `{{step_1}}`, etc. are replaced with actual values from previous steps
- **Smart Extraction**:
  - Handles dict results: looks for `path`, `result`, or `results[0].path`
  - Handles list results: extracts first item's path
  - Supports `result_key` with dot notation: `"results.0.path"` navigates nested structures
- **Dependency Tracking**: Uses `depends_on: [0, 1]` to identify which previous steps to reference

### How It Works

#### Example 1: Rename File (Search → Rename)

**User Request:**
```
"Rename the file Bodyweight Progression .pdf to Bodyweight_Progression.pdf"
```

**Generated Plan:**
```json
{
  "steps": [
    {
      "step_index": 0,
      "tool": "semantic_search",
      "args": {
        "path": "~",
        "query": "Bodyweight Progression .pdf"
      },
      "result_key": "results.0.path",
      "description": "Search for the PDF file"
    },
    {
      "step_index": 1,
      "tool": "rename_file",
      "args": {
        "old_path": "{{step_0}}",
        "new_name": "Bodyweight_Progression.pdf"
      },
      "depends_on": [0],
      "description": "Rename the file to remove spaces"
    }
  ]
}
```

**Execution Flow:**

1. **Step 0 executes:**
   - `semantic_search` returns:
     ```json
     {
       "results": [
         {"path": "/home/geek69/Documents/Bodyweight Progression .pdf", "score": 95}
       ],
       "total": 1
     }
     ```
   - `result_key: "results.0.path"` extracts: `"/home/geek69/Documents/Bodyweight Progression .pdf"`
   - Stored in `step_outputs[0]`

2. **Step 1 executes:**
   - `depends_on: [0]` detected
   - Placeholder `{{step_0}}` found in `args.old_path`
   - Replaced with `step_outputs[0]`: `"/home/geek69/Documents/Bodyweight Progression .pdf"`
   - Final args:
     ```json
     {
       "old_path": "/home/geek69/Documents/Bodyweight Progression .pdf",
       "new_name": "Bodyweight_Progression.pdf"
     }
     ```
   - `rename_file` executes successfully ✅

#### Example 2: Multi-File Operation (Search → Filter → Delete)

**User Request:**
```
"Delete all installer files older than 6 months"
```

**Generated Plan:**
```json
{
  "steps": [
    {
      "step_index": 0,
      "tool": "advanced_search",
      "args": {
        "path": "~/Downloads",
        "extensions": ".exe,.dmg,.pkg,.deb,.rpm",
        "modified_before": "6m"
      },
      "result_key": "results",
      "description": "Find installer files older than 6 months"
    },
    {
      "step_index": 1,
      "tool": "batch_delete",
      "args": {
        "files": "{{step_0}}"
      },
      "depends_on": [0],
      "is_destructive": true,
      "description": "Delete the old installers"
    }
  ]
}
```

### Supported Extraction Patterns

| Result Type | `result_key` | Extraction |
|-------------|--------------|------------|
| `{"path": "/file"}` | `"path"` | `"/file"` |
| `{"results": [{"path": "/f1"}, ...]}` | `"results.0.path"` | `"/f1"` |
| `{"data": {"value": 42}}` | `"data.value"` | `42` |
| `{"files": ["/f1", "/f2"]}` | `"files"` | `["/f1", "/f2"]` |
| No `result_key` | (none) | Full data dict |

### Automatic Fallbacks

If `result_key` extraction fails, the executor uses these fallbacks:

1. Look for `data.path`
2. Look for `data.result`
3. Look for `data.results[0].path`
4. If list: use `list[0].path`
5. If string: use as-is
6. Otherwise: use full `tool_result.data`

### Tools That Support Chaining

**Search Tools (Step 0 - Find files):**
- `semantic_search` → Returns `results[].path`
- `advanced_search` → Returns `results[].path`
- `search_files` → Returns `results[].path`
- `search_by_content` → Returns `results[].path`
- `search_documents` → Returns `results[].path`
- `find_duplicates` → Returns `duplicates[].files[].path`

**Operation Tools (Step 1+ - Use search results):**
- `rename_file` (accepts `old_path` from search)
- `move_file` (accepts `source` from search)
- `delete_file` (accepts `path` from search)
- `batch_delete` (accepts `files` array from search)
- `batch_rename` (accepts `files` array from search)
- Any tool accepting file paths

## Benefits

1. **User-Friendly**: Users don't need to know exact file paths
2. **Intelligent**: Agent reasons about multi-step workflows automatically
3. **Safe**: Search confirms file existence before destructive operations
4. **Flexible**: Supports complex workflows with multiple dependencies
5. **Robust**: Automatic fallbacks handle various data structures

## Testing

To test the fix:

```bash
cd OS_Agent/backend
source venv/bin/activate
python main.py
```

**Test Case 1: Rename without path**
```
User: "Rename myfile.txt to new_name.txt"
Expected: Searches for myfile.txt, then renames using found path
```

**Test Case 2: Move screenshots**
```
User: "Move all screenshots from last week into Images folder"
Expected: Searches for screenshots → filters by date → moves to Images/
```

**Test Case 3: Delete old installers**
```
User: "Delete installers older than 6 months"
Expected: Searches Downloads → filters by extension + age → deletes
```

## Future Enhancements

- **Orchestrator**: Full conversation-aware multi-step reasoning with conditionals
- **Error Recovery**: Retry search with different queries if first search fails
- **Batch Processing**: Parallel execution of independent steps
- **User Confirmation**: Show search results before destructive operations in interactive mode
