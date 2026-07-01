# Security Features Guide

Complete guide to FileAgent's security and privacy features.

---

## 🔒 Overview

FileAgent includes comprehensive security tools for:
- **Permission Management** - View and edit file permissions
- **Sensitive Data Detection** - Scan for secrets and credentials
- **File Encryption** - AES-256 encryption with password protection
- **Secure Deletion** - Military-grade file wiping
- **Audit Logging** - Complete operation history

---

## 📋 Permission Management

### View Permissions

View detailed information about file and directory permissions.

**Tool:** `view_permissions`

**Example commands:**
```
"Show permissions for my Documents folder"
"What are the permissions on config.yaml?"
"List all permissions recursively in /etc/nginx"
```

**Parameters:**
- `path`: File or directory path (required)
- `recursive`: Show all files in directory tree (default: false)

**Returns:**
- Permission string (e.g., "drwxr-xr-x")
- Numeric mode (e.g., "0755")
- Owner and group
- Individual read/write/execute flags

**Example API call:**
```json
{
  "tool": "view_permissions",
  "args": {
    "path": "/home/user/Documents",
    "recursive": true
  }
}
```

**Output example:**
```json
{
  "path": "/home/user/Documents/file.txt",
  "permissions_string": "-rw-r--r--",
  "permissions_numeric": "0644",
  "owner": "user",
  "group": "user",
  "user_read": true,
  "user_write": true,
  "user_execute": false
}
```

---

### Edit Permissions

Change file or directory permissions using numeric or symbolic modes.

**Tool:** `edit_permissions`

**Example commands:**
```
"Make script.sh executable"
"Change permissions of config.json to 600"
"Add read permission for group on all files in docs/"
```

**Parameters:**
- `path`: File or directory path (required)
- `mode`: Permission mode (required)
  - Numeric: "755", "644", "700", etc.
  - Symbolic: "u+x", "g-w", "a+r", "u=rwx,g=rx,o=r"
- `recursive`: Apply to all files in directory (default: false)

**Permission Modes:**

**Numeric mode:**
- First digit: user (owner) permissions
- Second digit: group permissions
- Third digit: others permissions
- Values: 4=read, 2=write, 1=execute (add them up)

Common modes:
- `755` = rwxr-xr-x (owner: full, others: read+execute)
- `644` = rw-r--r-- (owner: read+write, others: read-only)
- `600` = rw------- (owner: read+write, others: none)
- `700` = rwx------ (owner: full, others: none)

**Symbolic mode:**
- `u` = user/owner, `g` = group, `o` = others, `a` = all
- `+` = add permission, `-` = remove, `=` = set exactly
- `r` = read, `w` = write, `x` = execute

Examples:
- `u+x` = Add execute for owner
- `g-w` = Remove write for group
- `a+r` = Add read for everyone
- `u=rwx,g=rx,o=` = Owner: full, group: read+execute, others: none

**Example API calls:**
```json
{
  "tool": "edit_permissions",
  "args": {
    "path": "/home/user/script.sh",
    "mode": "755"
  }
}
```

```json
{
  "tool": "edit_permissions",
  "args": {
    "path": "/home/user/config.json",
    "mode": "u=rw,g=,o="
  }
}
```

---

## 🔍 Sensitive Data Detection

Scan files for passwords, API keys, private keys, and other sensitive information.

**Tool:** `detect_sensitive_files`

**Example commands:**
```
"Scan my code directory for API keys and passwords"
"Check config files for sensitive data"
"Find all files with credentials in the project"
```

**What it detects:**
- **Passwords** - password=, passwd:, pwd=
- **API Keys** - Long alphanumeric strings (32+ chars)
- **AWS Keys** - AKIA... format
- **Private Keys** - -----BEGIN PRIVATE KEY-----
- **JWTs** - eyJ... format tokens
- **GitHub Tokens** - ghp_, gho_, ghu_, ghs_ format
- **Generic secrets** - Common patterns

**Parameters:**
- `path`: Directory to scan (required)
- `recursive`: Scan subdirectories (default: true)
- `file_extensions`: Extensions to scan (default: .txt, .log, .py, .js, .env, .config, .json, .yaml, .sh)

**Example API call:**
```json
{
  "tool": "detect_sensitive_files",
  "args": {
    "path": "/home/user/projects/myapp",
    "recursive": true,
    "file_extensions": "py,js,env,config"
  }
}
```

**Output example:**
```json
{
  "files_scanned": 45,
  "total_findings": 3,
  "findings": [
    {
      "file": "/home/user/projects/myapp/config.py",
      "line": 12,
      "type": "password",
      "match": "password = 'mysecret123'"
    }
  ],
  "by_type": {
    "password": 2,
    "api_key": 1
  }
}
```

**Best Practices:**
- Run regularly on code repositories
- Check before committing to git
- Use .env files for secrets (not in version control)
- Rotate exposed credentials immediately
- Consider using secret management tools (HashiCorp Vault, AWS Secrets Manager)

---

## 🔐 File Encryption

Encrypt files using AES-256 encryption with password-based key derivation.

**Tool:** `encrypt_file`

**Example commands:**
```
"Encrypt my tax_documents.pdf with password"
"Encrypt all files in /secure folder"
"Lock private_notes.txt and delete the original"
```

**Features:**
- **AES-256 encryption** - Industry-standard strong encryption
- **PBKDF2 key derivation** - 100,000 iterations with SHA-256
- **Random salt** - Unique salt per file for additional security
- **Password-based** - No need to manage keys

**Parameters:**
- `path`: File to encrypt (required)
- `password`: Encryption password (required)
- `output_path`: Where to save encrypted file (default: adds .encrypted extension)
- `delete_original`: Delete original after encryption (default: false)

**Example API call:**
```json
{
  "tool": "encrypt_file",
  "args": {
    "path": "/home/user/Documents/confidential.docx",
    "password": "MyStr0ngP@ssw0rd",
    "delete_original": false
  }
}
```

**Security Notes:**
- **Use strong passwords** - At least 16 characters, mix of letters/numbers/symbols
- **Store passwords securely** - Use a password manager
- **Encrypted file format** - First 16 bytes: salt, rest: encrypted data
- **Cannot recover without password** - If you forget the password, file is unrecoverable

**Password recommendations:**
- ✅ Good: `My$ecur3!Encryption#Key2024`
- ✅ Good: `correct-horse-battery-staple-9876`
- ❌ Bad: `password123`
- ❌ Bad: `myname1990`

---

## 🔓 File Decryption

Decrypt files that were encrypted with the encrypt_file tool.

**Tool:** `decrypt_file`

**Example commands:**
```
"Decrypt confidential.docx.encrypted with my password"
"Unlock all .encrypted files in this folder"
"Decrypt and remove the encrypted version"
```

**Parameters:**
- `path`: Encrypted file path (required)
- `password`: Decryption password (required - must match encryption password)
- `output_path`: Where to save decrypted file (default: removes .encrypted extension)
- `delete_encrypted`: Delete encrypted file after decryption (default: false)

**Example API call:**
```json
{
  "tool": "decrypt_file",
  "args": {
    "path": "/home/user/Documents/confidential.docx.encrypted",
    "password": "MyStr0ngP@ssw0rd",
    "delete_encrypted": true
  }
}
```

**Error handling:**
- Wrong password → Decryption fails with clear error
- Corrupted file → Decryption fails
- File not encrypted → Decryption fails

---

## 🗑️ Secure Deletion

Permanently delete files using military-grade overwriting (DoD 5220.22-M standard).

**Tool:** `secure_delete`

**⚠️ WARNING:** This operation is **irreversible**. Files cannot be recovered after secure deletion.

**Example commands:**
```
"Securely delete sensitive_data.xlsx"
"Wipe old_passwords.txt with 7 passes"
"Permanently erase all .tmp files"
```

**How it works:**
1. Overwrites file data multiple times with different patterns
2. Pass 1: All zeros (0x00)
3. Pass 2: All ones (0xFF)
4. Pass 3+: Random data
5. Deletes the file
6. Verifies deletion

**Parameters:**
- `path`: File to securely delete (required)
- `passes`: Number of overwrite passes, 1-35 (default: 3)

**Pass recommendations:**
- **1 pass** - Quick wipe, good for SSDs
- **3 passes** - DoD standard, balanced security
- **7 passes** - Enhanced security
- **35 passes** - Paranoid mode (Gutmann method)

**Example API call:**
```json
{
  "tool": "secure_delete",
  "args": {
    "path": "/home/user/to_delete/secret.txt",
    "passes": 3
  }
}
```

**Important notes:**
- **SSDs**: Modern SSDs use wear-leveling, so secure deletion may not fully work. Consider full-disk encryption instead.
- **HDDs**: Secure deletion is effective on traditional hard drives.
- **Speed**: More passes = slower deletion. 3 passes is usually sufficient.
- **Confirmation required**: This is a destructive operation that requires explicit user approval.

---

## 📊 Audit Logging

View complete history of all agent operations.

**Tool:** `view_audit_log`

**Example commands:**
```
"Show me the last 50 operations"
"What files did I modify today?"
"Show all failed operations"
"Display audit log for delete operations"
```

**What's logged:**
- Every tool execution
- Timestamp
- Tool name
- Files affected
- Operation status (success/failed)
- Error messages (if failed)

**Parameters:**
- `limit`: Number of entries to retrieve (default: 100)
- `tool_name`: Filter by specific tool
- `file_path`: Filter by file path (partial match)
- `success_only`: Show only successful operations (default: false)

**Example API calls:**
```json
{
  "tool": "view_audit_log",
  "args": {
    "limit": 50,
    "success_only": true
  }
}
```

```json
{
  "tool": "view_audit_log",
  "args": {
    "tool_name": "secure_delete",
    "limit": 20
  }
}
```

```json
{
  "tool": "view_audit_log",
  "args": {
    "file_path": "/home/user/Documents",
    "limit": 100
  }
}
```

**Output example:**
```json
{
  "entries": [
    {
      "id": 123,
      "tool_name": "encrypt_file",
      "created_at": "2026-06-27T10:30:00",
      "status": "completed",
      "files_affected": "/home/user/Documents/report.pdf"
    }
  ],
  "total_count": 50,
  "tools_used": {
    "encrypt_file": 5,
    "view_permissions": 3,
    "secure_delete": 2
  }
}
```

**Use cases:**
- **Compliance** - Maintain audit trail for regulations
- **Debugging** - Track down issues
- **Security** - Review what operations were performed
- **Accountability** - See who did what and when

---

## 🔒 Security Best Practices

### General Security

1. **Principle of Least Privilege**
   - Only grant necessary permissions
   - Use 600 (rw-------) for sensitive files
   - Use 700 (rwx------) for private directories

2. **Regular Scans**
   - Run `detect_sensitive_files` on code repos before commits
   - Check for accidentally committed secrets
   - Rotate any exposed credentials immediately

3. **Encryption**
   - Encrypt sensitive files at rest
   - Use strong, unique passwords
   - Store passwords in password manager
   - Consider full-disk encryption for laptops

4. **Secure Deletion**
   - Use `secure_delete` for truly sensitive data
   - Understand SSD limitations
   - For SSDs, rely on encryption + normal deletion

5. **Audit Logging**
   - Review audit logs regularly
   - Look for unexpected operations
   - Monitor failed operations (potential attacks)

### File Permission Security

**Secure file permissions:**
```
600 (rw-------) - Private files (SSH keys, passwords)
644 (rw-r--r--) - Public readable files
700 (rwx------) - Private executables
755 (rwxr-xr-x) - Public executables
```

**Dangerous permissions:**
```
777 (rwxrwxrwx) - Everyone can do everything (NEVER use)
666 (rw-rw-rw-) - Everyone can write (avoid)
```

### Password Security

**For encryption:**
- Minimum 16 characters
- Mix of uppercase, lowercase, numbers, symbols
- Use password manager
- Don't reuse passwords
- Consider passphrases: "correct-horse-battery-staple"

---

## 🚨 Common Security Scenarios

### Scenario 1: Found Leaked Credentials

```
Problem: Accidentally committed AWS keys to GitHub

Steps:
1. "Scan my repo for AWS keys and API credentials"
2. Review findings
3. Rotate exposed credentials immediately
4. "Securely delete all files with exposed keys"
5. Rewrite git history to remove commits (git filter-branch)
6. Push force to remote
```

### Scenario 2: Sharing Encrypted Files

```
Task: Share confidential document securely

Steps:
1. "Encrypt quarterly_report.pdf with password"
2. Share encrypted file via email/cloud
3. Share password through separate channel (phone, Signal, etc.)
4. Recipient: "Decrypt quarterly_report.pdf.encrypted"
5. Both: "Securely delete decrypted file when done"
```

### Scenario 3: Decommissioning Computer

```
Task: Securely wipe sensitive files before selling laptop

Steps:
1. "Find all documents with 'confidential' or 'private' in name"
2. "Encrypt important files for backup"
3. "Securely delete all sensitive files with 7 passes"
4. "View audit log to verify all deletions"
5. Consider full disk wipe or disk encryption
```

### Scenario 4: Permission Audit

```
Task: Check for insecure file permissions

Steps:
1. "View permissions recursively in /home/user"
2. Look for 777, 666, or world-writable files
3. "Change permissions of config.json to 600"
4. "Change permissions of .ssh directory to 700 recursively"
5. "View audit log to document changes"
```

---

## 📝 Installation Notes

### Required Dependencies

**Always installed:**
- Python standard library (os, stat, secrets, re)
- aiosqlite (for audit log)

**Optional (for encryption/decryption):**
```bash
pip install cryptography
```

If not installed, encryption/decryption tools will return friendly error messages.

### System Permissions

Some operations require appropriate system permissions:
- **View permissions**: Requires read access to files
- **Edit permissions**: Requires write access to files
- **Audit log**: Requires read access to database
- **Everything else**: Respects system file permissions

---

## 🔮 Future Enhancements

Planned security features:
- [ ] GPG/PGP encryption support
- [ ] File integrity monitoring (checksums/hashes)
- [ ] Permission templates and presets
- [ ] Automated sensitive data masking
- [ ] Integration with system keyrings
- [ ] Two-factor encryption
- [ ] Encrypted archives/folders
- [ ] Security compliance reporting

---

**Remember**: Security is a process, not a product. Use these tools as part of a comprehensive security strategy.
