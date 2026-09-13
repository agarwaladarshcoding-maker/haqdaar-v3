"""tools/tunnel.py

Public address for the local server. Cloudflare quick tunnel by default (ngrok lost
half the audio on the long hop, 13 Sep); ngrok stays as the backup.
    python -m tools.tunnel          # start cloudflared if not up, point the line's number at it
    python -m tools.tunnel --host   # print the address in use (cloudflared if up, else ngrok)
    TUNNEL=ngrok python -m tools.tunnel   # backup: point the number back at NGROK_DOMAIN
The quick-tunnel address changes each time cloudflared restarts; this handles it.
"""
from __future__ import annotations
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from haqdaar.audio.telephony import point_number_at

LOGS = Path("logs")
HOST_FILE = LOGS / "tunnel_host"
PID_FILE = LOGS / "tunnel.pid"
LOG_FILE = LOGS / "cloudflared.log"
PORT = 8000


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def cloudflare_host() -> str:
    """Saved cloudflared address if that cloudflared is still running, else ""."""
    if HOST_FILE.exists() and PID_FILE.exists() and _alive(int(PID_FILE.read_text())):
        return HOST_FILE.read_text().strip()
    return ""


def start_cloudflare() -> str:
    LOGS.mkdir(exist_ok=True)
    log = open(LOG_FILE, "w")
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://localhost:{PORT}"],
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    for _ in range(60):
        m = re.search(r"https://([a-z0-9-]+\.trycloudflare\.com)", LOG_FILE.read_text())
        if m:
            PID_FILE.write_text(str(proc.pid))
            HOST_FILE.write_text(m.group(1))
            return m.group(1)
        if proc.poll() is not None:
            break
        time.sleep(0.5)
    proc.kill()
    raise RuntimeError(f"cloudflared gave no address, see {LOG_FILE}")


def main() -> int:
    load_dotenv()
    ngrok = os.environ.get("NGROK_DOMAIN", "")
    if "--host" in sys.argv:
        print(ngrok if os.environ.get("TUNNEL") == "ngrok" else cloudflare_host() or ngrok)
        return 0
    if os.environ.get("TUNNEL") == "ngrok":
        host = ngrok
    else:
        try:
            host = cloudflare_host() or start_cloudflare()
        except (OSError, RuntimeError) as e:
            print(f"tunnel  cloudflared failed ({e}); using ngrok {ngrok}")
            host = ngrok
    try:
        old = point_number_at(f"https://{host}/answer")
        if old != f"https://{host}/answer":
            print(f"tunnel  number now answers at {host} (was {old})")
    except Exception as e:  # keep the server usable even if the account call fails
        print(f"tunnel  could not update the number ({e}); dial-in may still use the old address")
    print(host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
