#!/usr/bin/env python3
"""
Quick test script to verify document and image understanding tools are properly registered.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from tools.base import registry
from tools.document_understanding_tools import ALL_DOCUMENT_UNDERSTANDING_TOOLS
from tools.image_understanding_tools import ALL_IMAGE_UNDERSTANDING_TOOLS


def test_tool_registration():
    """Test that all new tools are properly defined."""
    print("🧪 Testing Document Understanding Tools...")
    print(f"   Found {len(ALL_DOCUMENT_UNDERSTANDING_TOOLS)} document tools")

    for tool in ALL_DOCUMENT_UNDERSTANDING_TOOLS:
        print(f"   ✅ {tool.name}: {tool.description[:60]}...")
        assert tool.name, "Tool must have a name"
        assert tool.description, "Tool must have a description"
        assert tool.parameters_schema, "Tool must have parameters"
        assert hasattr(tool, "execute"), "Tool must have execute method"

    print("\n🧪 Testing Image Understanding Tools...")
    print(f"   Found {len(ALL_IMAGE_UNDERSTANDING_TOOLS)} image tools")

    for tool in ALL_IMAGE_UNDERSTANDING_TOOLS:
        print(f"   ✅ {tool.name}: {tool.description[:60]}...")
        assert tool.name, "Tool must have a name"
        assert tool.description, "Tool must have a description"
        assert tool.parameters_schema, "Tool must have parameters"
        assert hasattr(tool, "execute"), "Tool must have execute method"

    print("\n✅ All tools are properly defined!")

    # List all tool names
    print("\n📋 Document Understanding Tools:")
    for tool in ALL_DOCUMENT_UNDERSTANDING_TOOLS:
        print(f"   - {tool.name}")

    print("\n📋 Image Understanding Tools:")
    for tool in ALL_IMAGE_UNDERSTANDING_TOOLS:
        print(f"   - {tool.name}")

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Document tools: {len(ALL_DOCUMENT_UNDERSTANDING_TOOLS)}")
    print(f"  Image tools: {len(ALL_IMAGE_UNDERSTANDING_TOOLS)}")
    print(
        f"  Total new tools: {len(ALL_DOCUMENT_UNDERSTANDING_TOOLS) + len(ALL_IMAGE_UNDERSTANDING_TOOLS)}"
    )
    print("=" * 60)


if __name__ == "__main__":
    test_tool_registration()
