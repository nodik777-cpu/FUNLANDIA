import os
import time
import json
import hashlib
import logging
import threading
from datetime import datetime, timezone, timedelta

import requests

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("dahua_bridge")

DAHUA_HOST = os.getenv("DAHUA_HOST", "192.168.1.202")
DAHUA_USER = os.getenv("DAHUA_USER", "admin")
DAHUA_PASSWORD = os.getenv("DAHUA_PASSWORD", "")
STAFF_WEBHOOK = os.getenv("STAFF_WEBHOOK", "https://worker-production-a2c3.up.railway.app/dahua")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "20"))
VERIFY_TLS = os.getenv("VERIFY_TLS", "true").lower() != "false"


class DahuaRPC:
    def __init__(self, host, username, password):
        self.base = f"http://{host}"
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session_id = None
        self.request_id = 1
        self.lock = threading.Lock()

    def request(self, method, params=None, object_id=None):
        with self.lock:
            rid = self.request_id
            self.request_id += 1
        payload = {"method": method, "params": params, "id": rid}
        if object_id is not None:
            payload["object"] = object_id
        if self.session_id is not None:
            payload["session"] = self.session_id
        response = self.session.post(
            self.base + "/RPC2",
            json=payload,
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    def login(self):
        first = self.session.post(
            self.base + "/RPC2_Login",
            json={
                "method": "global.login",
                "params": {
                    "userName": self.username,
                    "password": "",
                    "clientType": "Web3.0",
                },
                "id": self.request_id,
            },
            timeout=15,
        ).json()
        self.request_id += 1
        self.session_id = first.get("session")
        params = first.get("params") or {}
        realm = params.get("realm", "")
        random_value = params.get("random", "")
        if not self.session_id or not realm or not random_value:
            raise RuntimeError(f"Dahua login challenge failed: {first}")

        h1 = hashlib.md5(
            f"{self.username}:{realm}:{self.password}".encode("utf-8")
        ).hexdigest().upper()
        h2 = hashlib.md5(
            f"{self.username}:{random_value}:{h1}".encode("utf-8")
        ).hexdigest().upper()

        second = self.session.post(
            self.base + "/RPC2_Login",
            json={
                "method": "global.login",
                "params": {
                    "userName": self.username,
                    "password": h2,
                    "clientType": "Web3.0",
                    "authorityType": "Default",
                    "passwordType": "Default",
                },
                "id": self.request_id,
                "session": self.session_id,
            },
            timeout=15,
        ).json()
        self.request_id += 1
        if not second.get("result"):
            raise RuntimeError(f"Dahua login failed: {second}")
        self.session_id = second.get("session") or self.session_id
        log.info("Dahua RPC2 login OK")

    def keep_alive(self):
        return self.request("global.keepAlive", {"timeout": 300, "active": False})

    def find_records(self, start_ts, end_ts, count=1000):
        created = self.request(
            "RecordFinder.factory.create",
            {"name": "AccessControlCardRec"},
        )
        result = created.get("result")
        if not result:
            raise RuntimeError(f"RecordFinder create failed: {created}")
        object_id = result

        started = self.request(
            "RecordFinder.startFind",
            {"condition": {"Time": ["<>", start_ts, end_ts]}},
            object_id=object_id,
        )
        if started.get("result") is False:
            raise RuntimeError(f"RecordFinder start failed: {started}")

        found = self.request(
            "RecordFinder.doFind",
            {"count": count},
            object_id=object_id,
        )
        result = found.get("result")
        if isinstance(result, dict):
            return result.get("records", []) or []
        if isinstance(found.get("records"), list):
            return found["records"]
        return []


def normalize(record):
    return {
        "UserID": str(record.get("UserID", "")),
        "CardName": str(record.get("CardName", record.get("Name", ""))),
        "CreateTime": str(record.get("CreateTime", record.get("LocaleTime", ""))),
        "Method": record.get("Method", ""),
        "Status": record.get("Status", record.get("ErrorCode", "")),
        "Type": record.get("Type", "Entry"),
        "RecNo": record.get("RecNo", ""),
        "source": "dahua-rpc2",
    }


def push(record):
    payload = normalize(record)
    response = requests.post(STAFF_WEBHOOK, json=payload, timeout=15)
    response.raise_for_status()


def main():
    if not DAHUA_PASSWORD:
        raise RuntimeError("DAHUA_PASSWORD is not set")

    rpc = DahuaRPC(DAHUA_HOST, DAHUA_USER, DAHUA_PASSWORD)
    last_ts = int(time.time()) - 300
    seen = set()

    while True:
        try:
            if not rpc.session_id:
                rpc.login()

            now = int(time.time())
            records = rpc.find_records(last_ts, now + 1)
            log.info("Dahua returned %s access records", len(records))

            max_ts = last_ts
            for record in records:
                normalized = normalize(record)
                key = f"{normalized['RecNo']}|{normalized['UserID']}|{normalized['CreateTime']}"
                if key in seen:
                    continue
                seen.add(key)
                try:
                    push(record)
                except Exception as exc:
                    log.warning("Could not push record %s: %s", key, exc)
                    continue
                try:
                    max_ts = max(max_ts, int(record.get("CreateTime", 0)))
                except (TypeError, ValueError):
                    pass

            # Keep a small overlap so records with equal timestamps are not missed.
            last_ts = max(0, max_ts - 2)
            if len(seen) > 5000:
                seen = set(list(seen)[-2500:])
            time.sleep(POLL_SECONDS)
        except Exception as exc:
            log.exception("Bridge cycle failed: %s", exc)
            rpc.session_id = None
            time.sleep(10)


if __name__ == "__main__":
    main()
