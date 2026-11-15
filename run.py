"""One command: gateway + wearables + browser. Picks a free port automatically."""
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

from cipherpulse import config  # loads .env


def free_port(host, start):
    """First port >= start that we can actually bind (skips busy and Windows-reserved ports)."""
    for p in range(start, start + 60):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    raise RuntimeError("no free port found")


def wait_open(host, port, timeout=40):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def main():
    import uvicorn

    port = free_port(config.HOST, config.PORT)
    os.environ["CP_PORT"] = str(port)
    config.PORT = port
    url = f"http://localhost:{port}"
    holder = {}

    def after_start():
        if not wait_open(config.HOST, port):
            return
        holder["p"] = subprocess.Popen([sys.executable, "-m", "cipherpulse.sensor.run_sensors"])
        if not os.environ.get("CP_NO_BROWSER"):
            time.sleep(0.8)
            webbrowser.open(url)

    threading.Thread(target=after_start, daemon=True).start()
    print("=" * 60)
    print(f"  CipherPulse is starting.  Open:  {url}")
    print("  Keep this window open. Press Ctrl+C to stop.")
    print("=" * 60, flush=True)
    try:
        uvicorn.run("cipherpulse.gateway.app:app", host=config.HOST, port=port, log_level="warning")
    finally:
        if holder.get("p"):
            holder["p"].terminate()


if __name__ == "__main__":
    main()
