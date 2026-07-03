"""
Agent Planner.
Takes natural language input → creates a structured execution plan.
The planner NEVER executes. It only creates tasks.
"""

import json
from typing import Dict, List, Optional

from llm.client import LLMClient
from tools.base import ToolRegistry

PLANNER_SYSTEM_PROMPT = """You are a filesystem planning agent. Your job is to take a user's natural language request about file operations and create a structured execution plan.

You have access to these tools:
{tools}

RULES:
1. NEVER execute anything. Only create plans.
2. All file paths must be absolute paths using ~ for home directory.
3. Break complex tasks into atomic steps.
4. Each step must use exactly one tool.
5. Order steps logically (scan before move, create dirs before moving files into them).
6. For destructive actions (delete, move), be explicit about what will be affected.
7. **CRITICAL: If a user mentions a file/folder by name but does NOT provide the full path, you MUST search for it first before performing any operation on it.**
   - To find a **FILE** by name: use `search_files` with a glob like `**/*filename*.ext` in `~/Downloads` or `~`.
   - To find a **DIRECTORY/FOLDER** by name: use `search_files` with pattern `**/{{folder_name}}` in `~` with `include_dirs: true` — NOT `semantic_search` (which only finds files, never folders).
   - **NEVER use `semantic_search` to locate a folder/directory** — it always returns 0 results for folder names.
   - For documents/downloads, prefer searching in `~/Downloads` or `~/Documents` before searching the entire home directory.
   - Use `recursive: true` to search subdirectories.
   - Be specific with the query — include file extension if mentioned.

8. **When a user wants to search INSIDE files in a named folder**: first locate the folder with `search_files` (include_dirs: true), then use `search_documents` on that folder path.

Respond ONLY with valid JSON in this exact format:
{{
    "goal": "short description of the goal",
    "summary": "human-readable summary of what the plan will do",
    "steps": [
        {{
            "step_index": 0,
            "tool": "tool_name",
            "description": "what this step does",
            "args": {{"arg1": "value1"}},
            "depends_on": [],
            "is_destructive": false,
            "result_key": "optional_key_to_extract_from_result"
        }}
    ],
    "warnings": ["any warnings or concerns"],
    "estimated_files_affected": 0
}}

**MULTI-STEP RESULT PASSING:**
When step B needs results from step A, use `depends_on` and `result_key`:
- Step A searches for a file → `result_key` extracts specific data from the search results
- Step B operates on the file → `depends_on: [0]` means "use step 0's extracted result"
- In step B's args, use placeholder `{{{{step_0}}}}` (literal text with 4 braces in JSON) which will be replaced with the extracted value
- `result_key` supports dot notation for nested extraction: "results.0.path" means "get first item in results array, then get its path field"
- IMPORTANT: When writing the placeholder in JSON, escape the braces: use the string "{{{{step_0}}}}" which becomes {{{{step_0}}}} in the actual JSON value

Example - Rename a file by searching for it first:
Step 0: {{"tool": "search_files", "args": {{"path": "~", "pattern": "**/*Bodyweight*Progression*.pdf"}}, "result_key": "0.path"}}
Step 1: {{"tool": "rename_file", "args": {{"path": "{{{{step_0}}}}", "new_name": "Bodyweight_Progression.pdf"}}, "depends_on": [0]}}

NOTE: For recursive search with search_files, use '**/' prefix in pattern:
  - "*.pdf" searches only in the specified directory
  - "**/*.pdf" searches in the directory AND all subdirectories recursively
  - "**/*keyword*.pdf" searches recursively for files containing 'keyword' in the name

Use 'search_files' with glob patterns for simple filename searches. Use 'semantic_search' only when you need natural language understanding of *file content*.

Example - Find a directory by name, then search inside it:
Step 0: {{"tool": "search_files", "args": {{"path": "~/Downloads", "pattern": "**/Job_Application_Resumes", "include_dirs": true}}, "result_key": "0.path"}}
Step 1: {{"tool": "search_documents", "args": {{"path": "{{{{step_0}}}}", "query": "Rahul Kumar"}}, "depends_on": [0]}}

If the search tool returns a list like `[{{"path": "/home/user/file.pdf"}}]`, use `result_key: "0.path"` on the search step to extract the first result's path. That extracted value then replaces `{{{{step_0}}}}` in the next step.

If the request is unclear, still create a plan but add questions to the warnings array.
If the request cannot be accomplished with the available tools, explain why in the summary and return an empty steps array.
"""


class Planner:
    """Creates execution plans from natural language input."""

    def __init__(self, llm_client: LLMClient, tool_registry: ToolRegistry):
        self.llm = llm_client
        self.tools = tool_registry

    async def create_plan(
        self,
        user_input: str,
        context: Optional[Dict] = None,
    ) -> Dict:
        """
        Create an execution plan from user input.

        Args:
            user_input: Natural language request from the user
            context: Optional context (memories, previous results, etc.)

        Returns:
            Dict with plan structure
        """
        tools_desc = self.tools.get_tools_for_prompt()

        system_prompt = PLANNER_SYSTEM_PROMPT.format(tools=tools_desc)

        messages = [{"role": "system", "content": system_prompt}]

        # Add context if available
        if context:
            context_str = f"Additional context:\n{json.dumps(context, indent=2)}"
            messages.append({"role": "system", "content": context_str})

        messages.append({"role": "user", "content": user_input})

        result = await self.llm.generate_json(messages)

        if result.get("error"):
            return {
                "success": False,
                "error": result["error"],
                "plan": None,
            }

        parsed = result.get("parsed")
        if not parsed:
            return {
                "success": False,
                "error": result.get("parse_error", "Failed to parse plan from LLM"),
                "raw_response": result.get("content", ""),
                "plan": None,
            }

        # Validate plan structure
        plan = self._validate_plan(parsed)
        return {
            "success": True,
            "plan": plan,
            "usage": result.get("usage", {}),
        }

    def _validate_plan(self, plan: Dict) -> Dict:
        """Validate and normalize plan structure."""
        # Ensure required fields
        plan.setdefault("goal", "unknown")
        plan.setdefault("summary", "")
        plan.setdefault("steps", [])
        plan.setdefault("warnings", [])
        plan.setdefault("estimated_files_affected", 0)

        # Validate each step
        valid_tools = {t["name"] for t in self.tools.list_tools()}
        validated_steps = []

        for i, step in enumerate(plan.get("steps", [])):
            step.setdefault("step_index", i)
            step.setdefault("tool", "")
            step.setdefault("description", "")
            step.setdefault("args", {})
            step.setdefault("depends_on", [])
            step.setdefault("is_destructive", False)

            # Check if tool exists
            if step["tool"] not in valid_tools:
                plan["warnings"].append(
                    f"Step {i}: Unknown tool '{step['tool']}'. Available: {', '.join(valid_tools)}"
                )

            # Auto-detect destructive operations
            if step["tool"] in ("delete_file", "move_file"):
                step["is_destructive"] = True

            validated_steps.append(step)

        plan["steps"] = validated_steps
        plan["has_destructive_steps"] = any(
            s["is_destructive"] for s in validated_steps
        )

        return plan
