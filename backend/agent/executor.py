"""
Agent Executor.
Takes an approved plan and executes it step-by-step.
Every action goes through the Policy Engine first.
Generates execution logs for audit/rollback.
"""
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from tools.base import ToolRegistry, ToolResult
from permissions.policy import PolicyEngine
from database.models import get_db


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

        db = await get_db()

        try:
            for i, step in enumerate(steps):
                step_id = str(uuid.uuid4())
                tool_name = step.get("tool", "")
                args = step.get("args", {})

                # Record step start
                await db.execute(
                    """INSERT INTO executions 
                       (id, task_id, step_index, tool_name, args_json, status, started_at)
                       VALUES (?, ?, ?, ?, ?, 'running', ?)""",
                    (step_id, task_id, i, tool_name, json.dumps(args), datetime.now().isoformat()),
                )
                await db.commit()

                # Policy check — validate all paths in args
                paths_to_check = []
                for key, val in args.items():
                    if isinstance(val, str) and ("/" in val or "~" in val):
                        paths_to_check.append(val)

                if paths_to_check:
                    policy_result = self.policy.validate_action(tool_name, paths_to_check)
                    if not policy_result["allowed"]:
                        error_msg = f"Policy denied: {policy_result['reason']}"
                        await db.execute(
                            "UPDATE executions SET status='denied', error=?, completed_at=? WHERE id=?",
                            (error_msg, datetime.now().isoformat(), step_id),
                        )
                        await db.commit()
                        errors.append({"step": i, "error": error_msg})
                        results.append({
                            "step_index": i,
                            "tool": tool_name,
                            "status": "denied",
                            "error": error_msg,
                        })
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
                    results.append({
                        "step_index": i,
                        "tool": tool_name,
                        "status": "error",
                        "error": error_msg,
                    })
                    continue

                # Execute the tool
                try:
                    tool_result: ToolResult = await tool.execute(args)

                    status = "completed" if tool_result.success else "failed"
                    await db.execute(
                        """UPDATE executions 
                           SET status=?, result_json=?, completed_at=? 
                           WHERE id=?""",
                        (status, json.dumps(tool_result.model_dump()), datetime.now().isoformat(), step_id),
                    )
                    await db.commit()

                    total_files_affected.extend(tool_result.files_affected)

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
                    results.append({
                        "step_index": i,
                        "tool": tool_name,
                        "status": "error",
                        "error": error_msg,
                    })

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            # Build execution report
            report = {
                "task_id": task_id,
                "status": "completed" if not errors else "completed_with_errors",
                "total_steps": len(steps),
                "completed_steps": sum(1 for r in results if r["status"] == "completed"),
                "failed_steps": sum(1 for r in results if r["status"] in ("failed", "error", "denied")),
                "total_files_affected": len(set(total_files_affected)),
                "files_affected": list(set(total_files_affected)),
                "duration_seconds": duration,
                "errors": errors,
                "steps": results,
            }

            # Update task record
            await db.execute(
                "UPDATE tasks SET status=?, result_json=?, updated_at=? WHERE id=?",
                (report["status"], json.dumps(report), datetime.now().isoformat(), task_id),
            )
            await db.commit()

            return report

        finally:
            await db.close()
