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
    # This terminal is a post-2024 Dahua device and requires Type-1 P2P auth.
    return [BINARY_PATH, "--app", P2P_APP, "-t", "1", "-u", DAHUA_USER, "-P", DAHUA_PASSWORD, "--log-retries", "--debug", "-p", f"{P2P_LOCAL_PORT}:80", DAHUA_SERIAL]


def p2p_worker():'''
if not re.search(pattern, s, flags=re.S):
    raise RuntimeError("Could not find the old Dahua P2P command in staff_bot.py")
s = re.sub(pattern, replacement, s, count=1, flags=re.S)

# Dahua Web 5.0 can send HTTP Push payloads as JSON, form data, XML, or
# multipart/chunked requests. The old handler only trusted Content-Length and
# therefore could silently discard chunked/multipart attendance events.
helper = r'''

def _read_dahua_http_body(handler):
    n = int(handler.headers.get("Content-Length", "0") or 0)
    if n > 0:
        return handler.rfile.read(n)
    if "chunked" in (handler.headers.get("Transfer-Encoding", "").lower()):
        chunks = []
        while True:
            line = handler.rfile.readline().strip()
            if not line:
                continue
            try:
                size = int(line.split(b";", 1)[0], 16)
            except Exception:
                break
            if size == 0:
                handler.rfile.readline()
                break
            chunks.append(handler.rfile.read(size))
            handler.rfile.readline()
        return b"".join(chunks)
    return b""


def _parse_dahua_push(raw, content_type):
    payloads = []
    p = parse_body(raw, content_type)
    if p and not (len(p) == 1 and "raw" in p):
        payloads.append(p)

    # Multipart payloads may contain a JSON/XML metadata part plus an image.
    # Extract only textual JSON/XML/form sections; do not store images.
    if raw and "multipart/" in (content_type or "").lower():
        text = raw.decode("utf-8", "replace")
        for m in re.finditer(r"\{.*?\}", text, re.S):
            candidate = m.group(0)
            try:
                payloads.append(json.loads(candidate))
            except Exception:
                pass
        for m in re.finditer(r"<\?xml.*?</[^>]+>", text, re.S | re.I):
            candidate = m.group(0)
            x = parse_xml(candidate.encode("utf-8", "replace"))
            if x:
                payloads.append(x)

    if not payloads and raw:
        s = raw.decode("utf-8", "replace").strip()
        if s:
            payloads.append({"raw": s[:12000]})
    return payloads
'''
marker = "\nclass Handler(BaseHTTPRequestHandler):"
if marker not in s:
    raise RuntimeError("Could not find Handler class")
s = s.replace(marker, helper + marker, 1)

post_pattern = r'    def do_POST\(self\):\n        try:.*?        except Exception as e:log\.exception\("Dahua webhook error: %s",e\);self\.reply\(200,"OK"\)'
post_replacement = '''    def do_POST(self):
        try:
            path = urlparse(self.path).path
            ct = self.headers.get("Content-Type", "")
            raw = _read_dahua_http_body(self)
            log.info("DAHUA POST path=%s content-type=%s length=%s body-bytes=%s", path, ct, self.headers.get("Content-Length", "0"), len(raw))
            payloads = _parse_dahua_push(raw, ct)
            inserted = 0
            for payload in payloads:
                info = normalize(payload)
                # DoorStatus/Pulse is only a heartbeat and has no employee record.
                if info["user_id"] or info["user_name"]:
                    raw_for_db = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                    if save_event(info, raw_for_db, "dahua_http_push"):
                        inserted += 1
                        log.info("DAHUA ATTENDANCE id=%s name=%s time=%s type=%s method=%s", info["user_id"], info["user_name"], info["event_time"], info["type_raw"], info["method"])
            if inserted:
                log.info("DAHUA PUSH processed=%s new-events=%s", path, inserted)
            elif raw:
                preview = raw.decode("utf-8", "replace").replace("\\n", " ")[:500]
                log.info("DAHUA PUSH no attendance record path=%s preview=%r", path, preview)
            self.reply(200, "OK")
        except Exception as e:
            log.exception("Dahua webhook error: %s", e)
            self.reply(200, "OK")'''
if not re.search(post_pattern, s, flags=re.S):
    raise RuntimeError("Could not find old Dahua do_POST handler")
s = re.sub(post_pattern, post_replacement, s, count=1, flags=re.S)

s = "BINARY_PATH = " + repr(str(BINARY)) + "\n" + s

code = compile(s, str(STAFF), "exec")
globals_dict = {"__name__": "__main__", "__file__": str(STAFF)}
exec(code, globals_dict)
