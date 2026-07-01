"""
Permission / Policy engine.
Validates every filesystem action against allowed/denied path rules.
No bypass. Ever.
"""
import os
import fnmatch
import yaml
from typing import List, Optional


class PolicyEngine:
    """Filesystem permission policy engine."""

    def __init__(self, config_path: str = None):
        self.allowed_paths: List[str] = []
        self.denied_paths: List[str] = []

        if config_path:
            self.load_config(config_path)

    def load_config(self, config_path: str):
        """Load permissions from YAML config file."""
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        fs_config = config.get("filesystem", {})
        self.allowed_paths = [
            os.path.expanduser(p) for p in fs_config.get("allowed_paths", [])
        ]
        self.denied_paths = [
            os.path.expanduser(p) for p in fs_config.get("denied_paths", [])
        ]

    def _normalize_path(self, path: str) -> str:
        """Normalize and expand a path."""
        return os.path.normpath(os.path.expanduser(path))

    def _is_under_path(self, target: str, base: str) -> bool:
        """Check if target is under base path (or is the base path itself).

        Supports glob patterns in base (e.g. '~/.*' to match hidden dirs).
        """
        target_norm = self._normalize_path(target)
        base_expanded = os.path.expanduser(base)

        # If the base contains a glob wildcard, use fnmatch on the full path
        # and also check every ancestor segment.
        if any(c in base_expanded for c in ("*", "?", "[")):
            path_to_test = target_norm
            while True:
                if fnmatch.fnmatch(path_to_test, base_expanded):
                    return True
                parent = os.path.dirname(path_to_test)
                if parent == path_to_test:  # reached filesystem root
                    break
                path_to_test = parent
            return False

        base_norm = self._normalize_path(base)
        return target_norm == base_norm or target_norm.startswith(base_norm + os.sep)

    def validate(self, path: str, action: str = "access") -> dict:
        """
        Validate if an action on a path is permitted.
        
        Returns:
            dict with 'allowed' (bool) and 'reason' (str)
        """
        normalized = self._normalize_path(path)

        # Check denied paths first (deny takes priority)
        for denied in self.denied_paths:
            if self._is_under_path(normalized, denied):
                return {
                    "allowed": False,
                    "reason": f"Path '{path}' is in denied zone: {denied}",
                }

        # Check allowed paths
        if self.allowed_paths:
            for allowed in self.allowed_paths:
                if self._is_under_path(normalized, allowed):
                    return {
                        "allowed": True,
                        "reason": f"Path '{path}' is in allowed zone: {allowed}",
                    }
            # If we have allowed paths but none matched
            return {
                "allowed": False,
                "reason": f"Path '{path}' is not in any allowed zone",
            }

        # No restrictions configured — allow by default
        return {
            "allowed": True,
            "reason": "No path restrictions configured",
        }

    def validate_action(self, action: str, paths: List[str]) -> dict:
        """
        Validate an entire action with multiple paths.
        
        Args:
            action: The action name (e.g., "move_file", "delete_file")
            paths: List of paths involved in the action
            
        Returns:
            dict with 'allowed' (bool), 'reason' (str), and 'details' (list)
        """
        details = []
        all_allowed = True

        for path in paths:
            result = self.validate(path, action)
            details.append({"path": path, **result})
            if not result["allowed"]:
                all_allowed = False

        # Extra safety: destructive actions get flagged
        destructive_actions = ["delete_file", "move_file"]
        requires_approval = action in destructive_actions

        return {
            "allowed": all_allowed,
            "requires_approval": requires_approval,
            "reason": "All paths validated" if all_allowed else "One or more paths denied",
            "details": details,
        }

    def add_allowed_path(self, path: str):
        """Dynamically add an allowed path."""
        expanded = os.path.expanduser(path)
        if expanded not in self.allowed_paths:
            self.allowed_paths.append(expanded)

    def remove_allowed_path(self, path: str):
        """Remove an allowed path."""
        expanded = os.path.expanduser(path)
        self.allowed_paths = [p for p in self.allowed_paths if p != expanded]

    def get_config(self) -> dict:
        """Return current permission configuration."""
        return {
            "allowed_paths": self.allowed_paths,
            "denied_paths": self.denied_paths,
        }
