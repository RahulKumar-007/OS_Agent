"""
Security Tools.
File permission management, encryption, secure deletion, sensitive data detection.
"""

import os
import re
import secrets
import stat
from datetime import datetime
from typing import Dict, List

from tools.base import Tool, ToolResult

# Check for cryptography library
HAS_CRYPTOGRAPHY = False
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2

    HAS_CRYPTOGRAPHY = True
except ImportError:
    pass


class ViewPermissionsTool(Tool):
    name = "view_permissions"
    description = (
        "View detailed file/directory permissions including owner, group, mode (rwx)"
    )
    parameters_schema = {
        "path": "Absolute path to file or directory",
        "recursive": "(optional) Show permissions for all files recursively. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        recursive = args.get("recursive", False)

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")

        results = []

        if os.path.isfile(path):
            results.append(self._get_permission_info(path))
        elif os.path.isdir(path):
            if recursive:
                for root, dirs, files in os.walk(path):
                    for item in dirs + files:
                        item_path = os.path.join(root, item)
                        try:
                            results.append(self._get_permission_info(item_path))
                        except:
                            continue
            else:
                results.append(self._get_permission_info(path))
                try:
                    for item in os.listdir(path):
                        item_path = os.path.join(path, item)
                        results.append(self._get_permission_info(item_path))
                except:
                    pass

        return ToolResult(
            success=True,
            data={"path": path, "permissions": results, "count": len(results)},
            message=f"Retrieved permissions for {len(results)} item(s)",
            files_affected=[path],
        )

    def _get_permission_info(self, path: str) -> Dict:
        st = os.stat(path)
        mode = st.st_mode
        perms = stat.filemode(mode)
        numeric_mode = oct(stat.S_IMODE(mode))

        try:
            import grp
            import pwd

            owner = pwd.getpwuid(st.st_uid).pw_name
            group = grp.getgrgid(st.st_gid).gr_name
        except:
            owner = str(st.st_uid)
            group = str(st.st_gid)

        return {
            "path": path,
            "name": os.path.basename(path),
            "type": "directory" if os.path.isdir(path) else "file",
            "permissions_string": perms,
            "permissions_numeric": numeric_mode,
            "owner": owner,
            "group": group,
            "user_read": bool(mode & stat.S_IRUSR),
            "user_write": bool(mode & stat.S_IWUSR),
            "user_execute": bool(mode & stat.S_IXUSR),
        }


class EditPermissionsTool(Tool):
    name = "edit_permissions"
    description = (
        "Change file/directory permissions using numeric (755) or symbolic (u+x) mode"
    )
    parameters_schema = {
        "path": "Absolute path to file or directory",
        "mode": "Permission mode: numeric ('755') or symbolic ('u+x,g-w')",
        "recursive": "(optional) Apply recursively. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        mode_str = args.get("mode", "")
        recursive = args.get("recursive", False)

        if not os.path.exists(path):
            return ToolResult(success=False, message=f"Path does not exist: {path}")
        if not mode_str:
            return ToolResult(success=False, message="Mode parameter is required")

        try:
            if mode_str.isdigit():
                new_mode = int(mode_str, 8)
            else:
                current_mode = os.stat(path).st_mode
                new_mode = self._parse_symbolic(mode_str, current_mode)
        except Exception as e:
            return ToolResult(success=False, message=f"Invalid mode: {str(e)}")

        changed_files = []
        try:
            if recursive and os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    for item in [root] + [os.path.join(root, f) for f in files]:
                        try:
                            os.chmod(item, new_mode)
                            changed_files.append(item)
                        except:
                            pass
            else:
                os.chmod(path, new_mode)
                changed_files.append(path)
        except Exception as e:
            return ToolResult(
                success=False, message=f"Failed to change permissions: {str(e)}"
            )

        return ToolResult(
            success=True,
            data={
                "path": path,
                "mode": oct(new_mode),
                "changed_count": len(changed_files),
            },
            message=f"Changed permissions for {len(changed_files)} item(s)",
            files_affected=changed_files,
        )

    def _parse_symbolic(self, symbolic: str, current_mode: int) -> int:
        mode = stat.S_IMODE(current_mode)
        for op in symbolic.split(","):
            match = re.match(r"^([ugoa]+)([+\-=])([rwx]+)$", op.strip())
            if not match:
                raise ValueError(f"Invalid symbolic mode: {op}")
            who, operator, perms = match.groups()
            perm_mask = 0
            for w in who:
                for p in perms:
                    if w == "u" or w == "a":
                        if p == "r":
                            perm_mask |= stat.S_IRUSR
                        if p == "w":
                            perm_mask |= stat.S_IWUSR
                        if p == "x":
                            perm_mask |= stat.S_IXUSR
                    if w == "g" or w == "a":
                        if p == "r":
                            perm_mask |= stat.S_IRGRP
                        if p == "w":
                            perm_mask |= stat.S_IWGRP
                        if p == "x":
                            perm_mask |= stat.S_IXGRP
                    if w == "o" or w == "a":
                        if p == "r":
                            perm_mask |= stat.S_IROTH
                        if p == "w":
                            perm_mask |= stat.S_IWOTH
                        if p == "x":
                            perm_mask |= stat.S_IXOTH
            if operator == "+":
                mode |= perm_mask
            elif operator == "-":
                mode &= ~perm_mask
        return mode


class DetectSensitiveFilesTool(Tool):
    name = "detect_sensitive_files"
    description = (
        "Scan files for sensitive data (passwords, API keys, private keys, secrets)"
    )
    parameters_schema = {
        "path": "Directory path to scan",
        "recursive": "(optional) Scan recursively. Default true.",
        "file_extensions": "(optional) Extensions to scan (e.g., 'txt,log,py'). Default: common text files.",
    }

    PATTERNS = {
        "api_key": re.compile(r"\b[A-Za-z0-9_-]{32,}\b"),
        "aws_key": re.compile(r"AKIA[0-9A-Z]{16}"),
        "password": re.compile(
            r'(?i)(password|passwd|pwd)\s*[:=]\s*[\'"]?([^\s\'"]+)[\'"]?'
        ),
        "private_key": re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
        "jwt": re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    }

    DEFAULT_EXTENSIONS = {
        ".txt",
        ".log",
        ".py",
        ".js",
        ".env",
        ".config",
        ".json",
        ".yaml",
        ".sh",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        recursive = args.get("recursive", True)
        extensions_str = args.get("file_extensions", "")

        if not os.path.exists(path) or not os.path.isdir(path):
            return ToolResult(success=False, message=f"Invalid directory: {path}")

        target_exts = set()
        if extensions_str:
            for ext in extensions_str.split(","):
                ext = ext.strip().lower()
                target_exts.add(ext if ext.startswith(".") else "." + ext)
        else:
            target_exts = self.DEFAULT_EXTENSIONS

        findings = []
        files_scanned = 0

        try:
            if recursive:
                for root, dirs, files in os.walk(path):
                    dirs[:] = [
                        d
                        for d in dirs
                        if not d.startswith(".") and d not in {"node_modules", "venv"}
                    ]
                    for fname in files:
                        if os.path.splitext(fname)[1].lower() in target_exts:
                            findings.extend(self._scan_file(os.path.join(root, fname)))
                            files_scanned += 1
            else:
                for fname in os.listdir(path):
                    fpath = os.path.join(path, fname)
                    if (
                        os.path.isfile(fpath)
                        and os.path.splitext(fname)[1].lower() in target_exts
                    ):
                        findings.extend(self._scan_file(fpath))
                        files_scanned += 1
        except:
            pass

        by_type = {}
        for f in findings:
            by_type[f["type"]] = by_type.get(f["type"], 0) + 1

        return ToolResult(
            success=True,
            data={
                "files_scanned": files_scanned,
                "total_findings": len(findings),
                "findings": findings[:100],
                "by_type": by_type,
            },
            message=f"Scanned {files_scanned} files, found {len(findings)} potential sensitive item(s)",
        )

    def _scan_file(self, filepath: str) -> List[Dict]:
        findings = []
        try:
            with open(filepath, "r", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    for pattern_name, pattern in self.PATTERNS.items():
                        for match in pattern.finditer(line):
                            findings.append(
                                {
                                    "file": filepath,
                                    "line": line_num,
                                    "type": pattern_name,
                                    "match": match.group(0)[:50],
                                }
                            )
        except:
            pass
        return findings


class EncryptFileTool(Tool):
    name = "encrypt_file"
    description = "Encrypt file using AES-256 with password. Creates .encrypted copy"
    parameters_schema = {
        "path": "File to encrypt",
        "password": "Encryption password",
        "output_path": "(optional) Output path. Default: adds .encrypted",
        "delete_original": "(optional) Delete original after encryption. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        if not HAS_CRYPTOGRAPHY:
            return ToolResult(
                success=False, message="Install: pip install cryptography"
            )

        path = os.path.expanduser(args.get("path", ""))
        password = args.get("password", "")
        output_path = args.get("output_path", path + ".encrypted")
        delete_original = args.get("delete_original", False)

        if not os.path.exists(path) or os.path.isdir(path) or not password:
            return ToolResult(success=False, message="Invalid file or missing password")

        try:
            salt = secrets.token_bytes(16)
            kdf = PBKDF2(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
                backend=default_backend(),
            )
            key = kdf.derive(password.encode())

            import base64

            cipher = Fernet(base64.urlsafe_b64encode(key))

            with open(path, "rb") as f:
                plaintext = f.read()
            encrypted = cipher.encrypt(plaintext)

            with open(output_path, "wb") as f:
                f.write(salt + encrypted)

            if delete_original:
                os.remove(path)

            return ToolResult(
                success=True,
                data={
                    "encrypted_file": output_path,
                    "original_deleted": delete_original,
                },
                message=f"File encrypted to {os.path.basename(output_path)}",
                files_affected=[path, output_path],
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Encryption failed: {str(e)}")


class DecryptFileTool(Tool):
    name = "decrypt_file"
    description = "Decrypt file encrypted with encrypt_file. Requires same password"
    parameters_schema = {
        "path": "Encrypted file path",
        "password": "Decryption password",
        "output_path": "(optional) Output path. Default: removes .encrypted",
        "delete_encrypted": "(optional) Delete encrypted file. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        if not HAS_CRYPTOGRAPHY:
            return ToolResult(
                success=False, message="Install: pip install cryptography"
            )

        path = os.path.expanduser(args.get("path", ""))
        password = args.get("password", "")
        output_path = args.get(
            "output_path",
            path.replace(".encrypted", "")
            if ".encrypted" in path
            else path + ".decrypted",
        )
        delete_encrypted = args.get("delete_encrypted", False)

        if not os.path.exists(path) or not password:
            return ToolResult(success=False, message="Invalid file or missing password")

        try:
            with open(path, "rb") as f:
                salt = f.read(16)
                encrypted = f.read()

            kdf = PBKDF2(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
                backend=default_backend(),
            )
            key = kdf.derive(password.encode())

            import base64

            cipher = Fernet(base64.urlsafe_b64encode(key))
            plaintext = cipher.decrypt(encrypted)

            with open(output_path, "wb") as f:
                f.write(plaintext)

            if delete_encrypted:
                os.remove(path)

            return ToolResult(
                success=True,
                data={
                    "decrypted_file": output_path,
                    "encrypted_deleted": delete_encrypted,
                },
                message=f"File decrypted to {os.path.basename(output_path)}",
                files_affected=[path, output_path],
            )
        except Exception as e:
            return ToolResult(
                success=False, message=f"Decryption failed (wrong password?): {str(e)}"
            )


class SecureDeleteTool(Tool):
    name = "secure_delete"
    description = "Securely delete file with multi-pass overwrite (DoD 5220.22-M). REQUIRES CONFIRMATION"
    parameters_schema = {
        "path": "File to securely delete",
        "passes": "(optional) Overwrite passes (1-35). Default 3.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        path = os.path.expanduser(args.get("path", ""))
        passes = int(args.get("passes", 3))

        if not os.path.exists(path) or os.path.isdir(path):
            return ToolResult(success=False, message="Invalid file")
        if passes < 1 or passes > 35:
            return ToolResult(success=False, message="Passes must be 1-35")

        try:
            file_size = os.path.getsize(path)

            with open(path, "r+b") as f:
                for i in range(passes):
                    pattern = (
                        b"\x00" * 4096
                        if i % 3 == 0
                        else (
                            b"\xff" * 4096 if i % 3 == 1 else secrets.token_bytes(4096)
                        )
                    )
                    f.seek(0)
                    remaining = file_size
                    while remaining > 0:
                        f.write(pattern[: min(4096, remaining)])
                        remaining -= 4096
                    f.flush()
                    os.fsync(f.fileno())

            os.remove(path)

            return ToolResult(
                success=True,
                data={"file": path, "size": file_size, "passes": passes},
                message=f"File securely deleted with {passes} pass(es)",
                files_affected=[path],
            )
        except Exception as e:
            return ToolResult(
                success=False, message=f"Secure deletion failed: {str(e)}"
            )


class ViewAuditLogTool(Tool):
    name = "view_audit_log"
    description = (
        "View audit log of all agent operations. Filter by date, tool, file, success"
    )
    parameters_schema = {
        "limit": "(optional) Number of entries. Default 100.",
        "tool_name": "(optional) Filter by tool name",
        "file_path": "(optional) Filter by file path (partial match)",
        "success_only": "(optional) Show only successful operations. Default false.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        limit = int(args.get("limit", 100))
        tool_name = args.get("tool_name", "")
        file_path = args.get("file_path", "")
        success_only = args.get("success_only", False)

        try:
            import aiosqlite

            query = "SELECT * FROM tasks WHERE 1=1"
            params = []

            if tool_name:
                query += " AND tool_name = ?"
                params.append(tool_name)
            if file_path:
                query += " AND files_affected LIKE ?"
                params.append(f"%{file_path}%")
            if success_only:
                query += " AND status = 'completed'"

            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            db_path = os.path.join(os.path.dirname(__file__), "..", "data", "agent.db")

            entries = []
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    columns = [d[0] for d in cursor.description]
                    for row in rows:
                        entries.append(dict(zip(columns, row)))

            tools_used = {}
            for e in entries:
                tool = e.get("tool_name", "unknown")
                tools_used[tool] = tools_used.get(tool, 0) + 1

            return ToolResult(
                success=True,
                data={
                    "entries": entries,
                    "total_count": len(entries),
                    "tools_used": tools_used,
                },
                message=f"Retrieved {len(entries)} audit log entries",
            )
        except Exception as e:
            return ToolResult(
                success=False, message=f"Failed to retrieve audit log: {str(e)}"
            )


ALL_SECURITY_TOOLS = [
    ViewPermissionsTool(),
    EditPermissionsTool(),
    DetectSensitiveFilesTool(),
    EncryptFileTool(),
    DecryptFileTool(),
    SecureDeleteTool(),
    ViewAuditLogTool(),
]
