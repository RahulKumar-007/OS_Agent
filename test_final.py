import os
from backend.permissions.policy import PolicyEngine

pe = PolicyEngine("backend/config.yaml")
print("Downloads:", pe.validate(os.path.expanduser("~/Downloads")))
print(".ssh:", pe.validate(os.path.expanduser("~/.ssh")))
print(".ssh/id_rsa:", pe.validate(os.path.expanduser("~/.ssh/id_rsa")))
print(".config/test:", pe.validate(os.path.expanduser("~/.config/test")))
print("Documents/work:", pe.validate(os.path.expanduser("~/Documents/work")))
print("Home:", pe.validate(os.path.expanduser("~")))
