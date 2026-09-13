"""Railway startup compatibility for the Dahua P2P helper.

The third-party dh-fwd repository declares its Go module as `dh-fwd`, while
its GitHub repository path is `github.com/undervolter/dh-fwd`.  staff_bot.py
uses the repository path with `go run`, so rewrite only that exact invocation
to the module path before Python starts the worker.
"""
import subprocess as _subprocess

_original_popen = _subprocess.Popen


def _patched_popen(args, *popenargs, **kwargs):
    if isinstance(args, (list, tuple)) and len(args) >= 3:
        if args[0] == "go" and args[1] == "run" and args[2] == "github.com/undervolter/dh-fwd@main":
            args = list(args)
            args[2] = "dh-fwd@main"
    return _original_popen(args, *popenargs, **kwargs)


_subprocess.Popen = _patched_popen
