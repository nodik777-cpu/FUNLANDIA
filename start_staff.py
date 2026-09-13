import os
import re
import json
import subprocess
import shutil
from pathlib import Path

# Staff Bot: HTTP Push + Dahua DMSS P2P tunnel.
# Main Funlandia bot is not touched.
os.environ["DAHUA_P2P_ENABLED"] = "1"
os.environ.setdefault("DAHUA_P2P_APP", "dmss")

# Build a tiny patched copy of the current dh-fwd client. The device reports
# an empty /info/device Info blob; upstream documents that this means no
# RandSalt and that the RandSalt XML tag must be omitted. The current client
# still fails closed on that exact case, so we patch only those two points.
def prepare_p2p():
    if not shutil.which("go") or not shutil.which("git"):
        raise RuntimeError("Go/git are not available")
    root = Path("/tmp/dh-fwd")
    if not (root / ".git").exists():
        subprocess.run(["git", "clone", "--depth", "1", "https://github.com/undervolter/dh-fwd.git", str(root)], check=True, timeout=120)
    else:
        subprocess.run(["git", "-C", str(root), "fetch", "--depth", "1", "origin", "main"], check=False, timeout=60)
        subprocess.run(["git", "-C", str(root), "reset", "--hard", "origin/main"], check=False, timeout=30)

    helpers = root / "helpers.go"
    hs = helpers.read_text(encoding="utf-8")
    old = '''\treturn fmt.Sprintf(\n\t\t"<CreateDate>%d</CreateDate><DevAuth>%s</DevAuth><Nonce>%d</Nonce><RandSalt>%s</RandSalt><UserName>%s</UserName>",\n\t\tcreated, auth, nonce, salt, username)'''
    new = '''\trandSaltTag := ""\n\tif salt != "" {\n\t\trandSaltTag = fmt.Sprintf("<RandSalt>%s</RandSalt>", salt)\n\t}\n\treturn fmt.Sprintf(\n\t\t"<CreateDate>%d</CreateDate><DevAuth>%s</DevAuth><Nonce>%d</Nonce>%s<UserName>%s</UserName>",\n\t\tcreated, auth, nonce, randSaltTag, username)'''
    if old in hs:
        hs = hs.replace(old, new, 1)
    helpers.write_text(hs, encoding="utf-8")

    tunnel = root / "tunnel.go"
    ts = tunnel.read_text(encoding="utf-8")
    old2 = '''\tif err != nil {\n\t\tif required {\n\t\t\treturn "", fmt.Errorf("randsalt: %v", err)\n\t\t}\n\t\tlogf("%s profile: randsalt from the Info blob unavailable (%v) — continuing", prof.name, err)\n\t\treturn randsalt, nil\n\t}'''
    new2 = '''\tif err != nil {\n\t\tif required && (strings.Contains(err.Error(), "Info field absent") || strings.Contains(err.Error(), "randsalt absent from the Info blob")) {\n\t\t\tlogf("%s profile: Info blob has no RandSalt; using empty salt and omitting RandSalt tag", prof.name)\n\t\t\treturn "", nil\n\t\t}\n\t\tif required {\n\t\t\treturn "", fmt.Errorf("randsalt: %v", err)\n\t\t}\n\t\tlogf("%s profile: randsalt from the Info blob unavailable (%v) — continuing", prof.name, err)\n\t\treturn randsalt, nil\n\t}'''
    if old2 in ts:
        ts = ts.replace(old2, new2, 1)
    tunnel.write_text(ts, encoding="utf-8")

    out = Path("/tmp/dh-fwd-funlandia")
    subprocess.run(["go", "build", "-o", str(out), "."], cwd=str(root), check=True, timeout=180)
    return str(out)

try:
    os.environ["DAHUA_P2P_BIN"] = prepare_p2p()
    print("FUNLANDIA: patched Dahua P2P client built")
except Exception as e:
    # Keep the bot alive; the normal upstream command remains available as a fallback.
    print(f"FUNLANDIA: patched Dahua P2P build failed: {e}")

STAFF = Path("staff_bot.py")
s = STAFF.read_text(encoding="utf-8")

# Use the locally built patched P2P binary when available.
old_p2p = re.search(r'def p2p_command\(\):\n.*?(?=\n\ndef p2p_worker\(\):)', s, flags=re.S)
if old_p2p:
    new_p2p = '''def p2p_command():
    binary = os.getenv("DAHUA_P2P_BIN", "").strip()
    if binary:
        return [binary, "--app", P2P_APP, "-t", "1", "-u", DAHUA_USER, "-P", DAHUA_PASSWORD, "-p", f"{P2P_LOCAL_PORT}:80", DAHUA_SERIAL]
    return ["go", "run", "github.com/undervolter/dh-fwd@main", "--app", P2P_APP, "-t", "1", "-u", DAHUA_USER, "-P", DAHUA_PASSWORD, "-p", f"{P2P_LOCAL_PORT}:80", DAHUA_SERIAL]'''
    s = s[:old_p2p.start()] + new_p2p + s[old_p2p.end():]

# Replace only the HTTP POST handler at runtime so the existing Staff Bot
# remains otherwise untouched. This handles normal, chunked, JSON, XML,
# form-urlencoded and multipart Dahua pushes.
old = re.search(r'    def do_POST\(self\):\n.*?(?=    def log_message\(self,\*args\):)', s, flags=re.S)
if not old:
    raise RuntimeError("Dahua HTTP handler was not found in staff_bot.py")

new = '''    def do_POST(self):
        try:
            path = urlparse(self.path).path
            ct = self.headers.get("Content-Type", "")
            transfer = self.headers.get("Transfer-Encoding", "")
            n = int(self.headers.get("Content-Length", "0") or 0)
            if n > 0:
                raw = self.rfile.read(n)
            elif "chunked" in transfer.lower():
                parts = []
                while True:
                    line = self.rfile.readline().strip()
                    if not line:
                        continue
                    size = int(line.split(b";", 1)[0], 16)
                    if size == 0:
                        self.rfile.readline()
                        break
                    parts.append(self.rfile.read(size))
                    self.rfile.readline()
                raw = b"".join(parts)
            else:
                raw = b""

            log.info("DAHUA POST path=%s content-type=%s length=%s body-bytes=%s", path, ct, n, len(raw))
            payloads = []
            if raw:
                p = parse_body(raw, ct)
                if p and not (isinstance(p, dict) and set(p.keys()) == {"raw"}):
                    payloads.append(p)
                text = raw.decode("utf-8", "replace")
                if "multipart/" in ct.lower():
                    for m in re.finditer(r"\{.*?\}", text, re.S):
                        try:
                            payloads.append(json.loads(m.group(0)))
                        except Exception:
                            pass
                    for m in re.finditer(r"<\?xml.*?</[^>]+>", text, re.S | re.I):
                        try:
                            x = parse_xml(m.group(0).encode("utf-8", "replace"))
                            if x:
                                payloads.append(x)
                        except Exception:
                            pass
                if not payloads and text.strip():
                    payloads.append({"raw": text.strip()[:12000]})

            inserted = 0
            for payload in payloads:
                info = normalize(payload)
                if info["user_id"] or info["user_name"]:
                    raw_for_db = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                    if save_event(info, raw_for_db, "dahua_http_push"):
                        inserted += 1
                        log.info("DAHUA ATTENDANCE id=%s name=%s time=%s type=%s method=%s", info["user_id"], info["user_name"], info["event_time"], info["type_raw"], info["method"])

            if inserted:
                log.info("DAHUA PUSH processed=%s new-events=%s", path, inserted)
            elif raw:
                preview = raw.decode("utf-8", "replace").replace("\n", " ")[:500]
                log.info("DAHUA PUSH no attendance record path=%s preview=%r", path, preview)
            self.reply(200, "OK")
        except Exception as e:
            log.exception("Dahua webhook error: %s", e)
            self.reply(200, "OK")
'''

s = s[:old.start()] + new + s[old.end():]
code = compile(s, str(STAFF), "exec")
globals_dict = {"__name__": "__main__", "__file__": str(STAFF)}
exec(code, globals_dict)
