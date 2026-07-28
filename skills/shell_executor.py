# skills/shell_executor.py - Safe shell command execution
import subprocess
from loguru import logger

ALLOW = {"ls", "cat", "echo", "pwd", "whoami", "date", "uname", "df", "free", "ps", "git", "python", "pip", "curl", "head", "tail", "grep"}

def run(cmd: str, timeout: int = 30):
    try:
        first = cmd.strip().split()[0] if cmd.strip() else ""
        if first not in ALLOW:
            return {"ok": False, "error": f"command not allowed: {first}", "stdout": "", "stderr": ""}
        out = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"ok": out.returncode == 0, "stdout": out.stdout, "stderr": out.stderr, "code": out.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout", "stdout": "", "stderr": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}
