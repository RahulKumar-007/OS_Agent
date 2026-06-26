"""
Base tool interface and tool registry.
Every tool follows a standard interface for discovery, validation, and execution.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel


class ToolResult(BaseModel):
    """Standard result from tool execution."""
    success: bool
    data: Optional[Any] = None
    message: str = ""
    files_affected: list = []


class Tool(ABC):
    """Base class for all agent tools."""

    name: str = ""
    description: str = ""
    parameters_schema: Dict = {}

    @abstractmethod
    async def execute(self, args: Dict) -> ToolResult:
        """Execute the tool with given arguments."""
        pass

    def validate_args(self, args: Dict) -> bool:
        """Basic argument validation. Override for custom validation."""
        return True

    def to_dict(self) -> Dict:
        """Serialize tool info for LLM context."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
        }


class ToolRegistry:
    """Registry of all available tools."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list:
        """List all registered tools."""
        return [t.to_dict() for t in self._tools.values()]

    def get_tools_for_prompt(self) -> str:
        """Get formatted tool descriptions for LLM prompt."""
        lines = []
        for tool in self._tools.values():
            lines.append(f"- **{tool.name}**: {tool.description}")
            if tool.parameters_schema:
                for param, desc in tool.parameters_schema.items():
                    lines.append(f"  - `{param}`: {desc}")
        return "\n".join(lines)


# Global registry
registry = ToolRegistry()
