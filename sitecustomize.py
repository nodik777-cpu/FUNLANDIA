"""Runtime compatibility patch for Dahua HTTP Push."""
import logging
import re
import socket
import threading
import time
from urllib.parse import parse_qs, urlparse


def _install():
    deadline = time.time() + 30
    while time.time() < deadline:
        main = __import__("__main__")
        handler = getattr(main, "DahuaHandler", None)
        if handler is not None:
            _patch_handler(handler, main)
            return
        time.sleep(0.05)


def _patch_handler(handler, main):
    if getattr(handler, "_funlandia_http_push_patch", False):
        return
    logger = getattr(main, "logger", logging.getLogger("funlandia_staff"))
    original_chunked = getattr(handler, "_read_chunked", None)

    def read_body(self):
        transfer = self.headers.get("Transfer-Encoding", "")
        if "chunked" in transfer.lower() and original_chunked:
            return original_chunked(self)
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length > 0:
            return self.rfile.read(length)
        chunks = []
        old_timeout = self.connection.gettimeout()
        try:
            self.connection.settimeout(0.35)
            while True:
                try:
                    chunk = self.rfile.read1(65536)
                except (socket.timeout, TimeoutError):
                    break
                if not chunk:
                    break
                chunks.append(chunk)
                if len(chunk) < 65536:
                    continue
        finally:
            try:
                self.connection.settimeout(old_timeout)
            except Exception:
                pass
        return b"".join(chunks)

    def collect_query_and_headers(self):
        data = {}
        parsed = parse_qs(urlparse(self.path).query, keep_blank_values=True)
        for key, values in parsed.items():
            if values:
                data[key] = values[-1]
        interesting = {
            "userid", "user_id", "username", "cardname", "eventtime",
            "event_type", "eventtype", "type", "status", "recno",
            "recordno", "createtime", "time", "action", "data"
        }
        for key, value in self.headers.items():
            normalized = re.sub(r"[^a-z0-9_]", "", key.lower())
            if normalized in interesting and value:
                data[key] = value
        return data

    def do_get(self):
        path = urlparse(self.path).path
        logger.info("DAHUA GET path=%s", path)
        query_data = collect_query_and_headers(self)
        if query_data and (path.startswith("/dahua") or "GeneralHttpUpload" in path):
            try:
                for event in main.extract_payloads(query_data):
                    inserted, info = main.save_event(event)
                    if info["user_id"] or info["user_name"]:
                        logger.info(
                            "DAHUA QUERY EVENT inserted=%s id=%s name=%s time=%s type=%s status=%s",
                            inserted, info["user_id"], info["user_name"], info["event_time"],
                            info["event_type"], info["status"]
                        )
            except Exception:
                logger.exception("DAHUA query event parse error")
        self._reply(200, "FUNLANDIA STAFF OK" if path.startswith("/health") else "OK")

    def do_post(self):
        try:
            raw = self._read_body()
            content_type = self.headers.get("Content-Type", "")
            path = urlparse(self.path).path
            logger.info(
                "DAHUA POST path=%s content-type=%s transfer=%s content-length=%s body-bytes=%s",
                path, content_type, self.headers.get("Transfer-Encoding", ""),
                self.headers.get("Content-Length", ""), len(raw)
            )
            payload = main.parse_body(raw, content_type) if raw else collect_query_and_headers(self)
            if not payload:
                self._reply(200, "OK")
                return
            inserted_count = 0
            for event in main.extract_payloads(payload):
                inserted, info = main.save_event(event)
                if inserted:
                    inserted_count += 1
                if info["user_id"] or info["user_name"]:
                    logger.info(
                        "DAHUA EVENT inserted=%s id=%s name=%s time=%s type=%s status=%s",
                        inserted, info["user_id"], info["user_name"], info["event_time"],
                        info["event_type"], info["status"]
                    )
            logger.info("DAHUA PUSH processed=%s new-events=%s", path, inserted_count)
            self._reply(200, "OK")
        except Exception as exc:
            logger.exception("DAHUA webhook error: %s", exc)
            self._reply(200, "OK")

    handler._read_body = read_body
    handler.do_GET = do_get
    handler.do_POST = do_post
    handler._funlandia_http_push_patch = True
    logger.info("FUNLANDIA: Dahua HTTP Push compatibility patch installed")


threading.Thread(target=_install, daemon=True).start()
