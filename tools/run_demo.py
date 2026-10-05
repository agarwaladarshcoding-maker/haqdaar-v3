"""tools/run_demo.py — one command to ring your phone into the server: `make call-me`.

1. fresh working tunnel (restarts cloudflared if its address died)
2. starts the server named by APP (default `haqdaar.server`), output to screen + logs/server.log
3. waits until the server is up (/health) and the tunnel reaches it
4. times a few tiny requests to the tunnel, Sarvam and Groq; a weak net means no ring (WEAK_OK=1 rings anyway)
5. points the number at it (asks first if another folder may hold it) and rings YOUR phone (CALL_ME_NUMBER, or TO=+91...)
Ctrl+C stops everything. `make call-me NOCALL=1` skips the ring; `make call` rings again.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

from haqdaar.audio.telephony import place_call
from haqdaar.contracts import tunables
from tools.tunnel import _resolves, cloudflare_blocked, cloudflare_host, start_cloudflare, start_ngrok, take_number

PORT = 8000
APP = os.environ.get("APP", "haqdaar.server:app")


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


def port_in_use(port: int) -> bool:
    """True if something already listens on 127.0.0.1:port (don't start a 2nd server)."""
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _reached(url: str, headers: dict | None = None) -> bool:
    """True on any HTTP reply (even 404 or 401): the place answered. False: no answer in 5 s."""
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=5).close()
    except urllib.error.HTTPError:
        pass
    except Exception:
        return False
    return True


def network_report(checks: dict[str, Callable[[], bool]], tries: int) -> dict[str, float | None]:
    """Worst time in seconds for each place over `tries` tries, or None if any try failed."""
    report: dict[str, float | None] = {}
    for name, fetch in checks.items():
        worst: float | None = 0.0
        for _ in range(tries):
            t0 = time.monotonic()
            try:
                good = fetch()
            except Exception:
                good = False
            if not good:
                worst = None
                break
            worst = max(worst, time.monotonic() - t0)
        report[name] = worst
    return report


def weak(report: dict[str, float | None], slow_s: float) -> list[str]:
    """Names that failed a try or were slower than slow_s."""
    return [n for n, t in report.items() if t is None or t > slow_s]


def wait_for(what: str, check, seconds: float) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            if check():
                return True
        except Exception:
            pass
        time.sleep(1)
    print(f"run-demo  !! gave up waiting for {what}", flush=True)
    return False


def main() -> int:
    load_dotenv(".env")
    to = os.environ.get("TO") or os.environ.get("CALL_ME_NUMBER", "")
    Path("logs").mkdir(exist_ok=True)

    ngrok = os.environ.get("NGROK_DOMAIN", "")
    host = ""
    # 5 Oct: on a network that opens only the web ports cloudflared never connects, and the call
    # was never placed. Then ngrok is used (it goes out on port 443). TUNNEL=ngrok asks for it.
    if os.environ.get("TUNNEL") == "ngrok" or (ngrok and cloudflare_blocked()):
        why = "asked for" if os.environ.get("TUNNEL") == "ngrok" else "this network blocks cloudflared (port 7844)"
        if start_ngrok(ngrok):
            host = ngrok
            print(f"run-demo  using ngrok: {why}", flush=True)
        else:
            print(f"run-demo  !! ngrok did not start ({why}); see logs/ngrok.log. Trying cloudflared.", flush=True)
    host = host or cloudflare_host()
    for attempt in range(3):  # quick-tunnel signup is slow some nights (15 Sep: timed out once)
        if host:
            break
        try:
            host = start_cloudflare()
            if not _resolves(host, tries=15):
                print(f"run-demo  tunnel {host} never came up; retrying", flush=True)
                os.kill(int(Path("logs/tunnel.pid").read_text()), 15)
                host = ""
        except (OSError, RuntimeError) as e:
            print(f"run-demo  cloudflared attempt {attempt + 1} failed: {e}", flush=True)
    if not host:
        host = os.environ.get("NGROK_DOMAIN", "")
        print(f"run-demo  !! cloudflared failed 3 times; using ngrok {host} (run `ngrok http --url={host} 8000` in another window)", flush=True)
    print(f"run-demo  tunnel {host}", flush=True)

    if port_in_use(PORT):
        print(f"run-demo  !! port {PORT} is already held (likely an old server). "
              f"Find it with `lsof -nP -iTCP:{PORT} -sTCP:LISTEN`, stop it, and re-run. "
              f"Not starting a second server.", flush=True)
        return 1

    env = dict(os.environ, NGROK_DOMAIN=host, PYTHONUNBUFFERED="1")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", APP, "--host", "127.0.0.1", "--port", str(PORT)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log = open("logs/server.log", "a")

    def pump() -> None:
        for line in server.stdout:
            sys.stdout.write(line); sys.stdout.flush()
            log.write(line); log.flush()
    threading.Thread(target=pump, daemon=True).start()

    try:
        ok = wait_for("the server", lambda: get(f"http://localhost:{PORT}/health"), 120)
        ip = _resolves(host, tries=15)

        def through_tunnel() -> bool:  # curl pinned to the public-DNS IP (see tunnel._resolves)
            pin = ["--resolve", f"{host}:443:{ip}"] if ip else []
            out = subprocess.run(["curl", "-s", "-m", "5", *pin, f"https://{host}/health"],
                                 capture_output=True, text=True).stdout
            return '"ok"' in out
        ok = ok and wait_for("the tunnel to reach the server", through_tunnel, 90 if host == ngrok else 30)
        if not ok:
            print("run-demo  !! not ready: the tunnel did not reach the server (logs/cloudflared.log, logs/ngrok.log)."
                  + ("" if host == ngrok else " Stop this (Ctrl+C) and run again with TUNNEL=ngrok in front.")
                  + " If that fails too, use a phone hotspot.", flush=True)
        else:
            tries = tunables.NET_CHECK_TRIES
            report = network_report({
                "tunnel": lambda: bool(through_tunnel()),
                "Sarvam": lambda: _reached("https://api.sarvam.ai/"),
                "Groq": lambda: _reached("https://api.groq.com/openai/v1/models",
                                         {"Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}"}),
            }, tries)
            shown = lambda t: "no reply" if t is None else f"{t:.2f} s"
            print("run-demo  network: " + ", ".join(f"{n} {shown(t)}" for n, t in report.items())
                  + f" (worst of {tries})", flush=True)
            bad = weak(report, tunables.NET_CHECK_SLOW_S)
            try:
                if not take_number(f"https://{host}/answer"):
                    print("run-demo  number not moved; the ring below still goes ahead (it carries its own address)", flush=True)
            except Exception as e:
                print(f"run-demo  could not point the number here ({e}); ringing still works", flush=True)
            if os.environ.get("NOCALL"):
                print("run-demo  ready. NOCALL set: not ringing. Run `make call` to ring.", flush=True)
            elif bad and not os.environ.get("WEAK_OK"):
                print("run-demo  !! weak network: " + ", ".join(f"{n} {shown(report[n])}" for n in bad)
                      + ". Not ringing. Use a phone hotspot or a wired net; WEAK_OK=1 rings anyway.", flush=True)
            elif not to:
                print("run-demo  !! no CALL_ME_NUMBER in .env (or TO=+91...); not ringing", flush=True)
            else:
                sid = place_call(to, f"https://{host}/answer")
                print(f"run-demo  RINGING {to[:-4]}xxxx now (call ..{sid[-6:]}). Pick up and talk.", flush=True)
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
