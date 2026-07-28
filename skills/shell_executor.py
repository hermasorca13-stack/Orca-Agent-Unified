# skills/shell_executor.py - Safe shell execution
import subprocess
from loguru import logger

ALLOW = {
    "ls", "cat", "echo", "pwd", "whoami", "date", "uname",
    "df", "free", "ps", "git", "python", "python3", "pip", "pip3",
    "curl", "head", "tail", "grep", "which", "env", "wc",
}

def run(cmd: str, timeout: int = 30) -> dict:
    """Whitelisted shell exec. Returns {ok, stdout, stderr, code}."""
    try:
        parts = cmd.strip().split()
        if not parts:
            return {"ok": False, "stdout": "", "stderr": "empty", "code": -1}
        if parts[0] not in ALLOW:
            return {"ok": False, "stdout": "", "stderr": f"not allowed: {parts[0]}", "code": -1}
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"ok": out.returncode == 0, "stdout": out.stdout, "stderr": out.stderr, "code": out.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "timeout", "code": -1}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "code": -1}
