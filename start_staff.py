import io
import re
import subprocess
import tarfile
import urllib.request
from pathlib import Path

STAFF = Path("staff_bot.py")
BINARY = Path("/tmp/dh-fwd-bin")
SRC = Path("/tmp/dh-fwd-src")

if not BINARY.exists():
    if SRC.exists():
        subprocess.run(["rm", "-rf", str(SRC)], check=True)
    print("DOWNLOADING Dahua P2P helper...", flush=True)
    url = "https://github.com/undervolter/dh-fwd/archive/refs/heads/main.tar.gz"
    data = urllib.request.urlopen(url, timeout=60).read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        members = tar.getmembers()
        root = next((m for m in members if m.name.endswith("/go.mod")), None)
        if root is None:
            raise RuntimeError("Downloaded dh-fwd archive does not contain go.mod")
        prefix = root.name.rsplit("/", 1)[0]
        for member in members:
            if not member.name.startswith(prefix + "/"):
                continue
            member.name = member.name[len(prefix) + 1:]
            if member.name:
                tar.extract(member, SRC)
    print("Dahua P2P helper source downloaded", flush=True)
    subprocess.run(["go", "build", "-o", str(BINARY), "."], cwd=str(SRC), check=True)
    BINARY.chmod(0o755)
    print("Dahua P2P helper built successfully", flush=True)

s = STAFF.read_text(encoding="utf-8")
pattern = r'def p2p_command\(\):\n    return \["go","run","github\.com/undervolter/dh-fwd@main".*?\n\n\ndef p2p_worker\(\):'
replacement = '''def p2p_command():
    # First try DMSS without Type-1 auth. This avoids the missing Info/RandSalt
    # path on this terminal. If the device rejects it, staff_bot will log the
    # exact P2P failure instead of looping through the broken autosalt step.
    return [BINARY_PATH, "--app", P2P_APP, "-t", "0", "-p", f"{P2P_LOCAL_PORT}:80", DAHUA_SERIAL]


def p2p_worker():'''
if not re.search(pattern, s, flags=re.S):
    raise RuntimeError("Could not find the old Dahua P2P command in staff_bot.py")
s = re.sub(pattern, replacement, s, count=1, flags=re.S)
s = "BINARY_PATH = " + repr(str(BINARY)) + "\n" + s

code = compile(s, str(STAFF), "exec")
globals_dict = {"__name__": "__main__", "__file__": str(STAFF)}
exec(code, globals_dict)
