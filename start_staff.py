import os
import re
import json
from pathlib import Path

# Staff Bot uses Dahua HTTP Push. Keep the experimental P2P tunnel disabled.
os.environ["DAHUA_P2P_ENABLED"] = "0"

STAFF = Path("staff_bot.py")
s = STAFF.read_text(encoding="utf-8")

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
                    for m in re.finditer(r"\\{.*?\\}", text, re.S):
                        try:
                            payloads.append(json.loads(m.group(0)))
                        except Exception:
                            pass
                    for m in re.finditer(r"<\\?xml.*?</[^>]+>", text, re.S | re.I):
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
                preview = raw.decode("utf-8", "replace").replace("\\n", " ")[:500]
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
