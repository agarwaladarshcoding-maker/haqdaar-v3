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
NGROK_LOG = LOGS / "ngrok.log"
NGROK_PID = LOGS / "ngrok.pid"
PORT = 8000


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _resolves(host: str, tries: int = 8) -> str:
    """IP of host from public DNS (1.1.1.1), or "". The Mac's own resolver caches the
    "not found" from a lookup made before a new quick tunnel exists, so it lies for minutes."""
    for _ in range(tries):
        try:
            out = subprocess.run(["dig", "+short", "@1.1.1.1", host], capture_output=True, text=True, timeout=5).stdout
            ips = [l for l in out.split() if re.fullmatch(r"[0-9.]+", l)]
            if ips:
                return ips[0]
        except (OSError, subprocess.TimeoutExpired):
            pass
        time.sleep(2)
    return ""


def _tunnel_up(host: str) -> bool:
    """False when Cloudflare itself says the tunnel is gone (http 530). The name of a dead quick
    tunnel still resolves (5 Oct: a 20-hour-old dead address was reused and no call was placed)."""
    try:
        out = subprocess.run(["curl", "-s", "-m", "6", "-o", "/dev/null", "-w", "%{http_code}", f"https://{host}/health"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return True     # no answer is not proof: keep it, the caller's own wait will tell
    return out != "530"


def cloudflare_blocked() -> bool:
    """True when this network does not let cloudflared out. It needs port 7844; some networks
    (5 Oct, the hackathon hall) open only the web ports, and the tunnel then never connects."""
    import socket

    try:    # the name has some twenty addresses: two tries of 2 s each are enough to know
        found = socket.getaddrinfo("region1.v2.argotunnel.com", 7844, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        return True
    for *_rest, address in found[:2]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2)
            if s.connect_ex(address) == 0:
                return False
    return True


def start_ngrok(host: str) -> bool:
    """Start ngrok on the saved address (it goes out on the web port 443). True: running."""
    if not host:
        return False
    if subprocess.run(["pgrep", "-f", f"ngrok http --url={host}"], capture_output=True).returncode == 0:
        return True
    LOGS.mkdir(exist_ok=True)
    try:
        proc = subprocess.Popen(["ngrok", "http", f"--url={host}", str(PORT), "--log", "stdout"],
                                stdout=open(NGROK_LOG, "w"), stderr=subprocess.STDOUT, start_new_session=True)
    except OSError:
        return False
    NGROK_PID.write_text(str(proc.pid))
    time.sleep(2)
    return proc.poll() is None


def cloudflare_host() -> str:
    """Saved cloudflared address if that cloudflared is still running and its address still
    exists, else "". A quick tunnel can die while the process lives on (15 Sep: dead host
    reused for 2 days); then stop that process so a fresh one starts."""
    if HOST_FILE.exists() and PID_FILE.exists() and _alive(pid := int(PID_FILE.read_text())):
        host = HOST_FILE.read_text().strip()
        if _resolves(host) and _tunnel_up(host):
            return host
        os.kill(pid, 15)
        PID_FILE.unlink()
    return ""


def start_cloudflare() -> str:
    LOGS.mkdir(exist_ok=True)
    log = open(LOG_FILE, "w")
    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://localhost:{PORT}"],
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    for _ in range(60):
        m = re.search(r"https://((?!api\.)[a-z0-9-]+\.trycloudflare\.com)", LOG_FILE.read_text())
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
