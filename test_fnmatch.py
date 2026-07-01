import os, fnmatch

def check(target, base):
    if any(c in base for c in ['*', '?', '[']):
        if fnmatch.fnmatch(target, base): return True
        parent = target
        while parent != os.path.dirname(parent):
            parent = os.path.dirname(parent)
            if fnmatch.fnmatch(parent, base): return True
        return False
    return target == base or target.startswith(base + os.sep)

print(check('/home/user/.ssh', '/home/user/.*'))
print(check('/home/user/.ssh/id_rsa', '/home/user/.*'))
print(check('/home/user/docs/.hidden', '/home/user/.*'))
print(check('/home/user/docs', '/home/user/.*'))
