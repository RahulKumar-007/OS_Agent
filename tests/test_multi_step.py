"""
Tests for multi-step reasoning and result passing.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from agent.executor import Executor
from permissions.policy import PolicyEngine
from tools.base import Tool, ToolRegistry, ToolResult


class MockSearchTool(Tool):
    """Mock search tool that returns a file path."""

    name = "mock_search"
    description = "Mock search for testing"
    parameters_schema = {"query": "Search query"}

    async def execute(self, args):
        return ToolResult(
            success=True,
            data={
                "results": [
                    {"path": "/home/user/found_file.txt", "score": 95},
                    {"path": "/home/user/another.txt", "score": 80},
                ],
                "total": 2,
            },
            message="Found 2 files",
        )


class MockRenameTool(Tool):
    """Mock rename tool for testing."""

    name = "mock_rename"
    description = "Mock rename for testing"
    parameters_schema = {"old_path": "Path to rename", "new_name": "New name"}

    async def execute(self, args):
        old_path = args.get("old_path", "")
        new_name = args.get("new_name", "")
        return ToolResult(
            success=True,
            data={"old": old_path, "new": new_name},
            message=f"Renamed {old_path} to {new_name}",
            files_affected=[old_path],
        )


@pytest.mark.asyncio
async def test_result_passing_with_result_key():
    """Test that result_key extracts nested values correctly."""
    registry = ToolRegistry()
    registry.register(MockSearchTool())
    registry.register(MockRenameTool())

    policy = PolicyEngine(restricted_paths=set())
    executor = Executor(registry, policy)

    plan = {
        "steps": [
            {
                "step_index": 0,
                "tool": "mock_search",
                "args": {"query": "test.txt"},
                "result_key": "results.0.path",  # Extract first result's path
                "depends_on": [],
            },
            {
                "step_index": 1,
                "tool": "mock_rename",
                "args": {
                    "old_path": "{{step_0}}",  # Should be replaced with /home/user/found_file.txt
                    "new_name": "renamed.txt",
                },
                "depends_on": [0],
            },
        ]
    }

    report = await executor.execute_plan("test-task", plan)

    # Verify execution succeeded
    assert report["status"] in ("completed", "completed_with_errors")
    assert report["completed_steps"] == 2
    assert len(report["steps"]) == 2

    # Verify step 1 received the correct path from step 0
    step_1_result = report["steps"][1]
    assert step_1_result["status"] == "completed"
    assert step_1_result["data"]["old"] == "/home/user/found_file.txt"
    assert step_1_result["data"]["new"] == "renamed.txt"


@pytest.mark.asyncio
async def test_result_passing_without_result_key():
    """Test that full data is passed when no result_key is specified."""
    registry = ToolRegistry()
    registry.register(MockSearchTool())
    registry.register(MockRenameTool())

    policy = PolicyEngine(restricted_paths=set())
    executor = Executor(registry, policy)

    plan = {
        "steps": [
            {
                "step_index": 0,
                "tool": "mock_search",
                "args": {"query": "test.txt"},
                # No result_key - should pass full data
                "depends_on": [],
            },
            {
                "step_index": 1,
                "tool": "mock_rename",
                "args": {
                    "old_path": "{{step_0}}",  # Should extract from results[0].path automatically
                    "new_name": "renamed.txt",
                },
                "depends_on": [0],
            },
        ]
    }

    report = await executor.execute_plan("test-task-2", plan)

    # Verify execution succeeded
    assert report["status"] in ("completed", "completed_with_errors")
    assert report["completed_steps"] == 2

    # Verify step 1 received extracted path even without result_key
    step_1_result = report["steps"][1]
    assert step_1_result["status"] == "completed"
    # The automatic fallback should extract results[0].path
    assert "/home/user/found_file.txt" in step_1_result["data"]["old"]


def test_result_key_parsing():
    """Test that result_key dot notation works correctly."""
    # Simulate the extraction logic
    data = {
        "results": [
            {"path": "/file1.txt", "score": 95},
            {"path": "/file2.txt", "score": 80},
        ],
        "total": 2,
    }

    result_key = "results.0.path"
    extracted = data
    for key_part in result_key.split("."):
        if isinstance(extracted, dict):
            extracted = extracted.get(key_part)
        elif isinstance(extracted, list):
            try:
                idx = int(key_part)
                extracted = extracted[idx] if idx < len(extracted) else None
            except (ValueError, IndexError):
                extracted = None
        else:
            extracted = None
        if extracted is None:
            break

    assert extracted == "/file1.txt"


if __name__ == "__main__":
    import asyncio

    # Run simple test
    async def main():
        print("Running result passing test...")
        await test_result_passing_with_result_key()
        print("✅ Test passed!")

        print("\nTesting result_key parsing...")
        test_result_key_parsing()
        print("✅ Parsing test passed!")

    asyncio.run(main())
