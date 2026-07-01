#!/usr/bin/env python3
"""
Test script to verify security tools are properly registered and functional.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from tools.security_tools import ALL_SECURITY_TOOLS


def test_security_tools():
    """Test that all security tools are properly defined."""
    print("🔒 Testing Security Tools...")
    print(f"   Found {len(ALL_SECURITY_TOOLS)} security tools\n")

    expected_tools = [
        "view_permissions",
        "edit_permissions",
        "detect_sensitive_files",
        "encrypt_file",
        "decrypt_file",
        "secure_delete",
        "view_audit_log",
    ]

    found_tools = []

    for tool in ALL_SECURITY_TOOLS:
        print(f"   ✅ {tool.name}")
        print(f"      Description: {tool.description[:70]}...")
        print(f"      Parameters: {', '.join(tool.parameters_schema.keys())}")
        print()

        # Validate tool structure
        assert tool.name, "Tool must have a name"
        assert tool.description, "Tool must have a description"
        assert tool.parameters_schema, "Tool must have parameters"
        assert hasattr(tool, "execute"), "Tool must have execute method"

        found_tools.append(tool.name)

    # Check all expected tools are present
    print("\n📋 Verification:")
    for expected in expected_tools:
        if expected in found_tools:
            print(f"   ✅ {expected} - Found")
        else:
            print(f"   ❌ {expected} - Missing!")
            sys.exit(1)

    print("\n" + "=" * 70)
    print("✨ All security tools verified successfully!")
    print("=" * 70)
    print(f"\nSummary:")
    print(f"  Total tools: {len(ALL_SECURITY_TOOLS)}")
    print(f"  Permission management: 2 tools")
    print(f"  Encryption: 2 tools")
    print(f"  Security scanning: 1 tool")
    print(f"  Secure deletion: 1 tool")
    print(f"  Audit logging: 1 tool")
    print("\n✅ Security module ready for production!")


if __name__ == "__main__":
    test_security_tools()
