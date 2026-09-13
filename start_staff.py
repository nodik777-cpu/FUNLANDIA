import os
import re
import subprocess
from pathlib import Path

STAFF = Path("staff_bot.py")
BINARY = Path("/tmp/dh-fwd-bin")
SRC = Path("/tmp/dh-fwd-src")

if not BINARY.exists():
    if SRC.exists():
        subprocess.run(["rm", "-rf", str(SRC)], check=True)
    print("BUILDING Dahua P2P helper...", flush=True)
    subprocess.run([
        "git", "clone", "--depth", "1",
        "https://github.com/undervolter/dh-fwd.git",
        str(SRC)
    ], check=True)
    subprocess.run(["go", "build", "-o", str(BINARY), "."], cwd=str(SRC), check=True)
    BINARY.chmod(0o755)
    print("Dahua P2P helper built successfully", flush=True)

s = STAFF.read_text(encoding="utf-8")
pattern = r'def p2p_command\(\):\n    return \["go","run","github\.com/undervolter/dh-fwd@main".*?\n\n\ndef p2p_worker\(\):'
replacement = '''def p2p_command():
    return [BINARY_PATH, "--app", P2P_APP, "-t", "1", "-u", DAHUA_USER, "-P", DAHUA_PASSWORD, "-p", f"{P2P_LOCAL_PORT}:80", DAHUA_SERIAL]


def p2p_worker():'''
if not re.search(pattern, s, flags=re.S):
    raise RuntimeError("Could not find the old Dahua P2P command in staff_bot.py")
s = re.sub(pattern, replacement, s, count=1, flags=re.S)
s = "BINARY_PATH = " + repr(str(BINARY)) + "\n" + s

code = compile(s, str(STAFF), "exec")
globals_dict = {"__name__": "__main__", "__file__": str(STAFF)}
exec(code, globals_dict)
