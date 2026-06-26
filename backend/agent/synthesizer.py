"""
Agent Synthesizer.
Post-processes raw tool output through the LLM to filter, summarize,
and format results based on the original user intent.

This is critical because:
1. Tools return raw data — they can't handle every nuanced filter
2. The LLM can interpret "exclude folders", "only PDFs from last week", etc.
3. Generates natural language summaries alongside structured data
"""
import json
from typing import Dict, Optional
from llm.client import LLMClient


SYNTHESIZER_PROMPT = """You are a results post-processor for a filesystem agent.

You receive the user's ORIGINAL request and RAW tool output.
Your job: FILTER and SUMMARIZE the results to match what the user actually asked for.

Examples of filtering you must do:
- "list files exclude folders" → remove all entries where is_dir=true
- "find PDFs larger than 10MB" → keep only .pdf files with size > 10485760
- "show images modified this week" → keep only image extensions from recent dates
- "find duplicate videos" → keep only video-related duplicate groups

Respond ONLY with valid JSON in this format:
{
    "summary": "Natural language summary written to the user. Include counts and key details.",
    "filtered_data": [<same structure as input but filtered>],
    "filters_applied": ["description of each filter applied"],
    "total_results": <count of items in filtered_data>,
    "notes": "Optional helpful observations or suggestions. Empty string if none."
}

CRITICAL RULES:
- filtered_data MUST keep the EXACT same object structure as the input (same keys).
- If the input is an array of file objects with {name, path, size, is_dir, modified}, your output must also be an array of the same objects, just filtered.
- If no filtering is needed, return the data unchanged.
- Do NOT invent data. Only return items that exist in the raw results.
- Keep the summary concise (1-3 sentences).
"""


class Synthesizer:
    """Post-processes execution results through the LLM."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def process(
        self,
        user_input: str,
        plan: Dict,
        execution_report: Dict,
    ) -> Dict:
        """
        Process raw execution results through the LLM.
        
        Args:
            user_input: The original user request
            plan: The execution plan that was used
            execution_report: Raw execution report from the executor
            
        Returns:
            Dict with 'summary', 'filtered_data', 'filters_applied', etc.
        """
        # Check if any steps actually returned data
        has_data = any(
            step.get("data") is not None
            for step in execution_report.get("steps", [])
        )

        if not has_data:
            # No data to synthesize (e.g., move/delete operations)
            return self._action_response(execution_report)

        # Build a concise representation of the results for the LLM
        steps_data = []
        for step in execution_report.get("steps", []):
            step_info = {
                "tool": step.get("tool"),
                "status": step.get("status"),
                "message": step.get("message", ""),
            }

            data = step.get("data")
            if data is not None:
                # For large file listings, truncate to avoid token limits
                # but keep enough for meaningful filtering
                if isinstance(data, list) and len(data) > 150:
                    step_info["data"] = data[:150]
                    step_info["data_truncated"] = True
                    step_info["total_items"] = len(data)
                    step_info["note"] = f"Showing first 150 of {len(data)} items. Apply filters to this subset."
                else:
                    step_info["data"] = data

            steps_data.append(step_info)

        context = {
            "user_request": user_input,
            "plan_goal": plan.get("goal", ""),
            "results": steps_data,
        }

        messages = [
            {"role": "system", "content": SYNTHESIZER_PROMPT},
            {"role": "user", "content": json.dumps(context, default=str)},
        ]

        result = await self.llm.generate_json(messages, temperature=0.1)

        if result.get("error"):
            return self._fallback_response(execution_report)

        parsed = result.get("parsed")
        if not parsed:
            return self._fallback_response(execution_report)

        # Ensure required fields exist
        parsed.setdefault("summary", "Task completed.")
        parsed.setdefault("filtered_data", None)
        parsed.setdefault("filters_applied", [])
        parsed.setdefault("total_results", 0)
        parsed.setdefault("notes", "")

        # If the LLM returned filtered_data as null/empty but we had data,
        # fall back to raw data (the LLM might have struggled)
        if parsed["filtered_data"] is None:
            for step in execution_report.get("steps", []):
                if step.get("data"):
                    parsed["filtered_data"] = step["data"]
                    parsed["total_results"] = len(step["data"]) if isinstance(step["data"], list) else 1
                    break

        return {
            "success": True,
            "synthesis": parsed,
            "usage": result.get("usage", {}),
        }

    def _action_response(self, report: Dict) -> Dict:
        """Response for action-only operations (move, delete, copy) that don't return data."""
        completed = report.get("completed_steps", 0)
        failed = report.get("failed_steps", 0)
        files = report.get("files_affected", [])

        if failed == 0:
            summary = f"Done! Successfully completed {completed} operation{'s' if completed != 1 else ''}."
            if files:
                summary += f" {len(files)} file{'s' if len(files) != 1 else ''} affected."
        else:
            summary = f"Completed with issues: {completed} succeeded, {failed} failed."

        return {
            "success": True,
            "synthesis": {
                "summary": summary,
                "filtered_data": None,
                "filters_applied": [],
                "total_results": 0,
                "notes": "",
            },
            "usage": {},
        }

    def _fallback_response(self, report: Dict) -> Dict:
        """Generate a basic response when LLM synthesis fails."""
        all_data = []
        for step in report.get("steps", []):
            if step.get("data"):
                all_data.append(step["data"])

        return {
            "success": False,
            "synthesis": {
                "summary": f"Task completed. {report.get('completed_steps', 0)} steps executed successfully.",
                "filtered_data": all_data[0] if len(all_data) == 1 else (all_data or None),
                "filters_applied": [],
                "total_results": len(all_data[0]) if all_data and isinstance(all_data[0], list) else 0,
                "notes": "Showing raw results (LLM post-processing was unavailable).",
            },
            "usage": {},
        }
