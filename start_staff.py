import os
from pathlib import Path

# Staff Bot uses Dahua HTTP Push. Keep the experimental P2P tunnel disabled.
os.environ["DAHUA_P2P_ENABLED"] = "0"

STAFF = Path("staff_bot.py")
code = compile(STAFF.read_text(encoding="utf-8"), str(STAFF), "exec")
globals_dict = {"__name__": "__main__", "__file__": str(STAFF)}
exec(code, globals_dict)
