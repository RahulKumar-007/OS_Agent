# Multi-Step Execution Flow

## Visual Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│  USER REQUEST: "Rename Bodyweight Progression .pdf to              │
│                  Bodyweight_Progression.pdf"                         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PLANNER (LLM)                                                       │
│  ✓ Detects missing file path                                        │
│  ✓ Creates 2-step plan: Search → Rename                             │
│  ✓ Links steps with depends_on + result_key                         │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GENERATED PLAN                                                      │
│  {                                                                   │
│    "steps": [                                                        │
│      {                                                               │
│        "step_index": 0,                                              │
│        "tool": "semantic_search",                                    │
│        "args": {"path": "~", "query": "Bodyweight Progression .pdf"},│
│        "result_key": "results.0.path"  ◄─── Extract path            │
│      },                                                              │
│      {                                                               │
│        "step_index": 1,                                              │
│        "tool": "rename_file",                                        │
│        "args": {                                                     │
│          "old_path": "{{step_0}}",  ◄─── Placeholder                │
│          "new_name": "Bodyweight_Progression.pdf"                    │
│        },                                                            │
│        "depends_on": [0]  ◄─── Waits for step 0                     │
│      }                                                               │
│    ]                                                                 │
│  }                                                                   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  USER APPROVAL                                                       │
│  □ Review plan                                                       │
│  ☑ Approve execution                                                 │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│  EXECUTOR - STEP 0                                                   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ semantic_search(path="~", query="Bodyweight Progression .pdf") │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                            │
│                         ▼                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ RESULT:                                                        │   │
│  │ {                                                              │   │
│  │   "results": [                                                 │   │
│  │     {                                                          │   │
│  │       "path": "/home/user/Documents/Bodyweight Progression .pdf"  │
│  │       "score": 95                                             │   │
│  │     }                                                          │   │
│  │   ]                                                            │   │
│  │ }                                                              │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                            │
│                         ▼                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ result_key="results.0.path" extracts:                          │   │
│  │ "/home/user/Documents/Bodyweight Progression .pdf"            │   │
│  │                                                                │   │
│  │ Stored in step_outputs[0]                                     │   │
│  └────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  EXECUTOR - STEP 1                                                   │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Original args:                                                 │   │
│  │ {                                                              │   │
│  │   "old_path": "{{step_0}}",                                    │   │
│  │   "new_name": "Bodyweight_Progression.pdf"                     │   │
│  │ }                                                              │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                            │
│                         ▼                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ depends_on: [0] detected                                       │   │
│  │ Replace {{step_0}} with step_outputs[0]                        │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                            │
│                         ▼                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Final args:                                                    │   │
│  │ {                                                              │   │
│  │   "old_path": "/home/user/Documents/Bodyweight Progression .pdf"  │
│  │   "new_name": "Bodyweight_Progression.pdf"                     │   │
│  │ }                                                              │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
│                         │                                            │
│                         ▼                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ rename_file() executes                                         │   │
│  │ ✓ SUCCESS                                                      │   │
│  └────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  EXECUTION REPORT                                                    │
│  ✅ 2 steps completed                                                │
│  ✅ File renamed successfully                                        │
│  📁 /home/user/Documents/Bodyweight_Progression.pdf                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Result Key Extraction

The `result_key` uses dot notation to navigate nested data structures:

| Input Data | `result_key` | Extracted Value |
|------------|--------------|-----------------|
| `{"path": "/file"}` | `"path"` | `"/file"` |
| `{"results": [{"path": "/f1"}]}` | `"results.0.path"` | `"/f1"` |
| `{"data": {"value": 42}}` | `"data.value"` | `42` |

### 2. Placeholder Replacement

Placeholders follow the pattern `{{step_N}}` where N is the step index.

**Example:**
```json
{
  "old_path": "{{step_0}}",
  "new_name": "{{step_1}}"
}
```

Before execution:
- `{{step_0}}` → Value from step 0's extracted result
- `{{step_1}}` → Value from step 1's extracted result

### 3. Dependency Tracking

Steps can depend on multiple previous steps:

```json
{
  "depends_on": [0, 2, 5]
}
```

This ensures:
- Step 0, 2, and 5 complete before this step runs
- Their results are available for placeholder replacement

## Example Workflows

### Example 1: Complex Search & Filter

```
User: "Delete all installer files older than 6 months"

Plan:
  Step 0: advanced_search(
    path="~/Downloads",
    extensions=".exe,.dmg,.pkg",
    modified_before="6m"
  ) → result_key="results"
  
  Step 1: batch_delete(
    files={{step_0}}
  ) → depends_on=[0]

Execution:
  Step 0 → Returns ["/Downloads/app1.exe", "/Downloads/old.dmg"]
  Step 1 → Deletes both files
```

### Example 2: Multi-Source Aggregation

```
User: "Find all my Python files and organize them by project"

Plan:
  Step 0: search_files(pattern="*.py", path="~") → result_key="results"
  
  Step 1: organize_by_ai(
    files={{step_0}},
    method="content_analysis"
  ) → depends_on=[0]

Execution:
  Step 0 → Finds 150 .py files
  Step 1 → Analyzes imports, creates project folders, moves files
```

## Automatic Fallbacks

If `result_key` extraction fails or is not specified, the executor tries:

1. `data.get("path")`
2. `data.get("result")`
3. `data["results"][0].get("path")` (if results is a list)
4. `data["results"][0].get("full_path")`
5. Full `data` dict as last resort

This ensures robustness across different tool output formats.

## Benefits

1. **User-Friendly**: No need to remember exact file paths
2. **Intelligent**: Agent autonomously plans complex workflows
3. **Safe**: Files are searched/verified before destructive operations
4. **Flexible**: Supports arbitrary step chains and data transformations
5. **Auditable**: Every step is logged with full input/output
