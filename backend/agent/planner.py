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
            "is_destructive": false
        }}
    ],
    "warnings": ["any warnings or concerns"],
    "estimated_files_affected": 0
}}

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
        plan["has_destructive_steps"] = any(s["is_destructive"] for s in validated_steps)

        return plan
