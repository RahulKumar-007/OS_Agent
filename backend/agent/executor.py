"""
Agent Executor.
Takes an approved plan and executes it step-by-step.
Every action goes through the Policy Engine first.
Generates execution logs for audit/rollback.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from database.models import get_db
from permissions.policy import PolicyEngine
from tools.base import ToolRegistry, ToolResult


class Executor:
    """Executes approved plans step by step."""

    def __init__(self, tool_registry: ToolRegistry, policy_engine: PolicyEngine):
        self.tools = tool_registry
        self.policy = policy_engine

    async def execute_plan(
        self,
        task_id: str,
        plan: Dict,
        on_step_complete=None,
    ) -> Dict:
        """
        Execute an approved plan.

        Args:
            task_id: ID of the task being executed
            plan: The plan dict with steps
            on_step_complete: Optional async callback(step_index, result)

        Returns:
            Execution report
        """
        steps = plan.get("steps", [])
        results = []
        total_files_affected = []
        errors = []
        start_time = datetime.now()

        # Store results from previous steps for result chaining
        step_outputs = {}  # {step_index: result_data}

        db = await get_db()

        try:
            for i, step in enumerate(steps):
                step_id = str(uuid.uuid4())
                tool_name = step.get("tool", "")
                args = step.get("args", {}).copy()  # Copy to avoid modifying original

                # Replace placeholders like {{step_0}} or {step_0} with actual results from previous steps
                depends_on = step.get("depends_on", [])
                if depends_on:
                    for dep_idx in depends_on:
                        if dep_idx in step_outputs:
                            # Support both {{step_N}} and {step_N} syntax
                            placeholder_double = f"{{{{step_{dep_idx}}}}}"
                            placeholder_single = f"{{step_{dep_idx}}}"
                            dep_data = step_outputs[dep_idx]

                            # Replace placeholders in all string arg values
                            for key, value in args.items():
                                if isinstance(value, str) and (
                                    placeholder_double in value
                                    or placeholder_single in value
                                ):
                                    # If the dependency result is a dict with a 'path' or first result, use that
                                    replacement = None
                                    if isinstance(dep_data, dict):
                                        # Try common keys: direct path, result key, or first item in results array
                                        replacement = dep_data.get(
                                            "path"
                                        ) or dep_data.get("result")
                                        if not replacement and "results" in dep_data:
                                            results_list = dep_data["results"]
                                            if (
                                                isinstance(results_list, list)
                                                and results_list
                                            ):
                                                first_item = results_list[0]
                                                if isinstance(first_item, dict):
                                                    replacement = first_item.get(
                                                        "path"
                                                    ) or first_item.get("full_path")
                                                else:
                                                    replacement = str(first_item)
                                    elif isinstance(dep_data, list) and dep_data:
                                        # If it's a list, get first item's path
                                        first = dep_data[0]
                                        if isinstance(first, dict):
                                            replacement = first.get(
                                                "path"
                                            ) or first.get("full_path")
                                        else:
                                            replacement = str(first)
                                    elif isinstance(dep_data, str):
                                        replacement = dep_data

                                    if replacement:
                                        # Replace both single and double brace versions
                                        value = value.replace(
                                            placeholder_double, str(replacement)
                                        )
                                        value = value.replace(
                                            placeholder_single, str(replacement)
                                        )
                                        args[key] = value

                # Guard: if any placeholder is still unresolved, fail this step early
                # rather than passing a literal "{{step_N}}" string to a tool.
                import re as _re
                unresolved = [
                    v for v in args.values()
                    if isinstance(v, str) and _re.search(r'\{\{?step_\d+\}?\}', v)
                ]
                if unresolved:
                    dep_indices = step.get("depends_on", [])
                    dep_str = ", ".join(f"step {d}" for d in dep_indices)
                    error_msg = (
                        f"Cannot execute: {dep_str} returned no results — "
                        f"placeholder could not be resolved. "
                        f"The prerequisite search may need a broader path or different query."
                    )
                    await db.execute(
                        "UPDATE executions SET status='error', error=?, completed_at=? WHERE id=?",
                        (error_msg, datetime.now().isoformat(), step_id),
                    )
                    await db.commit()
                    errors.append({"step": i, "error": error_msg})
                    results.append(
                        {
                            "step_index": i,
                            "tool": tool_name,
                            "status": "error",
                            "error": error_msg,
                        }
                    )
                    continue

                # Record step start
                await db.execute(
                    """INSERT INTO executions
                       (id, task_id, step_index, tool_name, args_json, status, started_at)
                       VALUES (?, ?, ?, ?, ?, 'running', ?)""",
                    (
                        step_id,
                        task_id,
                        i,
                        tool_name,
                        json.dumps(args),
                        datetime.now().isoformat(),
                    ),
                )
                await db.commit()

                # Policy check — validate only args that are real filesystem paths.
                # We must NOT validate glob patterns (e.g. "**/*.pdf") or bare
                # filenames just because they contain "/" or "~".
                # Rule: a value is a "path" only if it resolves to an absolute path
                # after expanduser (i.e. starts with "/" after expansion).
                paths_to_check = []
                for key, val in args.items():
                    if not isinstance(val, str) or not val.strip():
                        continue
                    expanded = os.path.expanduser(val)
                    # Only treat as a real path if it starts with "/" (i.e. absolute)
                    if expanded.startswith("/"):
                        paths_to_check.append(expanded)

                # For rename_file: new_name is a bare filename with no '/' so it
                # would be skipped above, but the tool constructs a full destination
                # path internally. Reconstruct it here so the policy can validate it.
                if tool_name == "rename_file":
                    src = os.path.expanduser(args.get("path", ""))
                    new_name = args.get("new_name", "")
                    if src and new_name:
                        constructed_dest = os.path.normpath(
                            os.path.join(os.path.dirname(src), new_name)
                        )
                        paths_to_check.append(constructed_dest)
                        # Also ensure source is included even if it has no '/' in raw form
                        if src not in paths_to_check:
                            paths_to_check.append(src)

                if paths_to_check:
                    policy_result = self.policy.validate_action(
                        tool_name, paths_to_check
                    )
                    if not policy_result["allowed"]:
                        error_msg = f"Policy denied: {policy_result['reason']}"
                        await db.execute(
                            "UPDATE executions SET status='denied', error=?, completed_at=? WHERE id=?",
                            (error_msg, datetime.now().isoformat(), step_id),
                        )
                        await db.commit()
                        errors.append({"step": i, "error": error_msg})
                        results.append(
                            {
                                "step_index": i,
                                "tool": tool_name,
                                "status": "denied",
                                "error": error_msg,
                            }
                        )
                        continue

                # Get the tool
                tool = self.tools.get(tool_name)
                if not tool:
                    error_msg = f"Unknown tool: {tool_name}"
                    await db.execute(
                        "UPDATE executions SET status='error', error=?, completed_at=? WHERE id=?",
                        (error_msg, datetime.now().isoformat(), step_id),
                    )
                    await db.commit()
                    errors.append({"step": i, "error": error_msg})
                    results.append(
                        {
                            "step_index": i,
                            "tool": tool_name,
                            "status": "error",
                            "error": error_msg,
                        }
                    )
                    continue

                # Execute the tool
                try:
                    tool_result: ToolResult = await tool.execute(args)

                    status = "completed" if tool_result.success else "failed"
                    await db.execute(
                        """UPDATE executions
                           SET status=?, result_json=?, completed_at=?
                           WHERE id=?""",
                        (
                            status,
                            json.dumps(tool_result.model_dump()),
                            datetime.now().isoformat(),
                            step_id,
                        ),
                    )
                    await db.commit()

                    total_files_affected.extend(tool_result.files_affected)

                    # Store this step's output for dependent steps
                    # Extract specific result key if specified.
                    # Supports dot notation: "0.path" works on a list root,
                    # "results.0.path" works on a dict root with a "results" list key.
                    result_key = step.get("result_key")
                    if result_key and tool_result.data is not None:
                        extracted = tool_result.data
                        for key_part in result_key.split("."):
                            if isinstance(extracted, dict):
                                extracted = extracted.get(key_part)
                            elif isinstance(extracted, list):
                                try:
                                    idx = int(key_part)
                                    extracted = (
                                        extracted[idx] if idx < len(extracted) else None
                                    )
                                except (ValueError, IndexError):
                                    extracted = None
                            else:
                                extracted = None
                            if extracted is None:
                                break
                        step_outputs[i] = (
                            extracted if extracted is not None else tool_result.data
                        )
                    else:
                        step_outputs[i] = tool_result.data

                    step_result = {
                        "step_index": i,
                        "tool": tool_name,
                        "status": status,
                        "message": tool_result.message,
                        "data": tool_result.data,
                        "files_affected": tool_result.files_affected,
                    }
                    results.append(step_result)

                    if not tool_result.success:
                        errors.append({"step": i, "error": tool_result.message})

                    # Callback for real-time updates
                    if on_step_complete:
                        await on_step_complete(i, step_result)

                except Exception as e:
                    error_msg = str(e)
                    await db.execute(
                        "UPDATE executions SET status='error', error=?, completed_at=? WHERE id=?",
                        (error_msg, datetime.now().isoformat(), step_id),
                    )
                    await db.commit()
                    errors.append({"step": i, "error": error_msg})
                    results.append(
                        {
                            "step_index": i,
                            "tool": tool_name,
                            "status": "error",
                            "error": error_msg,
                        }
                    )

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Build execution report
            report = {
                "task_id": task_id,
                "status": "completed" if not errors else "completed_with_errors",
                "total_steps": len(steps),
                "completed_steps": sum(
                    1 for r in results if r["status"] == "completed"
                ),
                "failed_steps": sum(
                    1 for r in results if r["status"] in ("failed", "error", "denied")
                ),
                "total_files_affected": len(set(total_files_affected)),
                "files_affected": list(set(total_files_affected)),
                "duration_seconds": duration,
                "errors": errors,
                "steps": results,
            }

            # Update task record
            await db.execute(
                "UPDATE tasks SET status=?, result_json=?, updated_at=? WHERE id=?",
                (
                    report["status"],
                    json.dumps(report),
                    datetime.now().isoformat(),
                    task_id,
                ),
            )
            await db.commit()

            return report

        finally:
            await db.close()
