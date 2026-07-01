import os
import yaml
from backend.permissions.policy import PolicyEngine

pe = PolicyEngine("backend/config.yaml")
print(pe.validate(os.path.expanduser("~/.ssh/id_rsa")))
