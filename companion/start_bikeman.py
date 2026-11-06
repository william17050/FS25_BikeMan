"""
One-shot starter: runs the bike bridge in the background and the FS25 link in front. Ctrl+C stops both.

  python start_bikeman.py                  find the bike, then start the link
  python start_bikeman.py --units mph      options this script does not know are passed to fs25_link.py

The bridge's own messages go to rides/bridge_console.log once the bike is connected.
Normally started through linux_start.sh or windows_start.bat, which set up Python first.
"""
import argparse
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def stop(bridge):
    """Let the bridge put the bike's resistance back before it exits."""
    if bridge.poll() is None and hasattr(signal, "SIGINT") and os.name != "nt":
        bridge.send_signal(signal.SIGINT)
    try:
        bridge.wait(timeout=8)
    except subprocess.TimeoutExpired:
        bridge.terminate()


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0],
                                 epilog="Any other options are passed to fs25_link.py, e.g. --units mph --hud-scale 1.5")
    ap.add_argument("--port", type=int, default=48765)
    ap.add_argument("--cap", type=int, default=50, help="highest resistance the game may command (hard max 80)")
    ap.add_argument("--addr", default="", help="bike Bluetooth address; blank = find it automatically")
    ap.add_argument("--obc", default="", help="OpenBikeControl handlebar controller: auto, its Bluetooth address or IP:port; blank = none")
    ap.add_argument("--bridge-python", default=sys.executable, help="Python that has bleak installed")
    ap.add_argument("--wait", type=float, default=90, help="seconds to wait for the bike")
    a, link_args = ap.parse_known_args()

    os.chdir(HERE)
    os.makedirs("rides", exist_ok=True)
    log_path = os.path.join("rides", "bridge_console.log")
    cmd = [a.bridge_python, "-u", "bridge.py", "--cap", str(a.cap), "--port", str(a.port)]
    if a.addr:
        cmd += ["--addr", a.addr]
    if a.obc:
        cmd += ["--obc", a.obc]
    print("Starting the bike bridge. Wake the bike by pedalling. Close the Renpho app and Zwift first.")
    rc = 1
    with open(log_path, "w") as log:
        bridge = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
    try:
        shown, ready, t0 = 0, False, time.time()
        while time.time() - t0 < a.wait:
            time.sleep(0.3)
            lines = open(log_path, errors="replace").read().splitlines()
            for line in lines[shown:]:
                print("  " + line)
            shown = len(lines)
            if any("Bike connected." in line for line in lines):
                ready = True
                break
            if bridge.poll() is not None:
                print("The bridge stopped. See the messages above.")
                return 1
        if not ready:
            print(f"No bike after {a.wait:.0f} s. Wake it by pedalling and try again.")
            return 1
        print(f"Bridge messages from now on: {log_path}\nStarting the FS25 link ...")
        rc = subprocess.call([sys.executable, "fs25_link.py", "--port", str(a.port)] + link_args)
    except KeyboardInterrupt:
        rc = 0
    finally:
        stop(bridge)
    return rc


if __name__ == "__main__":
    sys.exit(main())
