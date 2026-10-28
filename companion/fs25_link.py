"""
FS25 <-> bike link. Run alongside bridge.py (bridge first) while FS25 is running with the FS25_BikeMan mod.

  python fs25_link.py                  bike speed drives the game vehicle, game grade drives bike resistance
  python fs25_link.py --fake-kph 20    no bike needed: hold the game vehicle at 20 km/h (tests cruise control)
  python fs25_link.py --no-grade       do not send grade to the bike
  python fs25_link.py --grade-scale 1.3  make hills harder/easier

Game -> us : modSettings/FS25_BikeMan/out.txt  (speed, body pitch as grade %)
Us -> game : modSettings/FS25_BikeMan/in.xml   (target km/h; the mod lets go if this stops changing for 2 s)
Us -> bike : {"grade": pct} to the bridge on 127.0.0.1:48765
Grade source is body pitch (terrain slope reads wrong on bridges). It is median-filtered over ~0.5 s,
clamped to --min-grade..--max-grade, and 0 when you are not in a vehicle.
Logs: rides/fs25_link_<time>.csv
"""
import argparse
import csv
import json
import os
import socket
import statistics
import threading
import time
from collections import deque

def find_profile(override=None):
    """FS25 user profile folder (the one holding mods/, modSettings/, log.txt). Windows (incl. OneDrive Documents) or Linux/Proton."""
    home = os.path.expanduser("~")
    cands = [override] if override else []
    cands += [
        os.path.join(home, "Documents", "My Games", "FarmingSimulator2025"),
        os.path.join(home, "OneDrive", "Documents", "My Games", "FarmingSimulator2025"),
        os.path.join(os.environ.get("OneDrive", home), "Documents", "My Games", "FarmingSimulator2025"),
        os.path.join(home, ".local/share/Steam/steamapps/compatdata/2300320/pfx/drive_c/users/steamuser/Documents/My Games/FarmingSimulator2025"),
    ]
    for c in cands:
        if c and os.path.isdir(c):
            return c
    raise SystemExit("Could not find the FS25 profile folder. Run once with --profile \"<path to My Games\\FarmingSimulator2025>\".")


DIR = OUT = IN = None


class Bridge(threading.Thread):
    """Keeps the latest bike data from bridge.py and lets us send grade."""

    def __init__(self, port):
        super().__init__(daemon=True)
        self.port, self.sock = port, None
        self.data = None          # last {"type":"data"...}
        self.data_t = 0.0
        self.lock = threading.Lock()

    def run(self):
        while True:
            try:
                s = socket.create_connection(("127.0.0.1", self.port), timeout=2)
                s.settimeout(None)
                self.sock = s
                self.send({"grade": 0.0})
                for line in s.makefile("r"):
                    try:
                        m = json.loads(line)
                    except ValueError:
                        continue
                    if m.get("type") == "data":
                        with self.lock:
                            self.data, self.data_t = m, time.time()
            except OSError:
                pass
            self.sock = None
            time.sleep(1.0)

    def send(self, obj):
        s = self.sock
        if s is not None:
            try:
                s.sendall((json.dumps(obj) + "\n").encode())
            except OSError:
                pass

    def latest(self, max_age=3.0):
        with self.lock:
            return self.data if self.data and time.time() - self.data_t < max_age else None


def read_out():
    """Returns dict from out.txt or None."""
    try:
        p = open(OUT).read().strip().split(",")
        return {"seq": int(p[0]), "speed": float(p[1]), "pitch": float(p[2]), "terrain": float(p[3]),
                "in_veh": int(p[4]), "vehicle": p[5], "cruise_state": int(p[6]), "cruise_kmh": float(p[7]),
                "engaged": int(p[8]), "odo_resets": int(p[9]) if len(p) > 9 else 0}
    except (OSError, ValueError, IndexError):
        return None


def write_in(seq, kph, rpm, watts, grade=0.0, kj=0.0, hud=1.0, units="both", brake=0.0, dist=0.0):
    tmp = IN + ".tmp"
    with open(tmp, "w") as f:
        f.write(f'<?xml version="1.0" encoding="utf-8"?>\n<in seq="{seq}" kph="{kph:.1f}" rpm="{rpm:.0f}" watts="{watts:.0f}" grade="{grade:.2f}" kj="{kj:.1f}" hud="{hud:.2f}" units="{units}" brake="{brake:.2f}" dist="{dist:.3f}"/>\n')
    for _ in range(5):             # Windows refuses the swap while the game has in.xml open; retry briefly, else skip this tick
        try:
            os.replace(tmp, IN)
            return
        except OSError:
            time.sleep(0.01)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=48765)
    ap.add_argument("--fake-kph", type=float, default=None, help="skip the bike; hold this speed in the game")
    ap.add_argument("--speed-scale", type=float, default=1.0, help="multiply the bike's speed for the game")
    ap.add_argument("--max-kph", type=float, default=45.0, help="cap on the game speed")
    ap.add_argument("--pedal-rpm", type=float, default=25.0, help="cadence that counts as pedalling (below this the game bike freewheels / holds)")
    ap.add_argument("--hud-scale", type=float, default=1.2, help="size of the in-game panel (1 = small, 2 = large, 3 = huge); changes apply on restart of this script, no game restart")
    ap.add_argument("--units", choices=["both", "mph", "kmh"], default="both", help="speed units shown on the in-game panel")
    ap.add_argument("--coast-brake", type=float, default=0.7, help="gentle braking (0-1) while rolling and not pedalling; 0 = pure freewheel. Automatically off on downhills steeper than -2%%")
    ap.add_argument("--distance", choices=["bike", "game"], default="bike", help="trip distance on the panel: bike speed while pedalling plus game speed while coasting (default), or always the game vehicle's speed")
    ap.add_argument("--no-grade", action="store_true")
    ap.add_argument("--grade-scale", type=float, default=0.6)
    ap.add_argument("--min-grade", type=float, default=-10.0)
    ap.add_argument("--max-grade", type=float, default=20.0)
    ap.add_argument("--profile", default=None, help="FS25 profile folder if it is not found automatically")
    a = ap.parse_args()
    global DIR, OUT, IN
    DIR = os.path.join(find_profile(a.profile), "modSettings", "FS25_BikeMan")
    OUT, IN = os.path.join(DIR, "out.txt"), os.path.join(DIR, "in.xml")

    os.makedirs(DIR, exist_ok=True)
    os.makedirs("rides", exist_ok=True)
    bridge = None
    if a.fake_kph is None:
        bridge = Bridge(a.port)
        bridge.start()
    logf = open(f"rides/fs25_link_{time.strftime('%Y%m%d_%H%M%S')}.csv", "w", newline="")
    log = csv.writer(logf)
    log.writerow(["t", "game_kph", "pitch_pct", "grade_sent", "target_kph", "bike_kph", "rpm", "watts", "engaged", "cruise_kmh", "trip_km", "odo_resets"])

    hist = deque(maxlen=5)         # ~0.5 s of pitch at 10 Hz
    last_seq, grade_sent, grade_t = None, None, 0.0
    seq, t0 = 0, time.time()
    pedalling, low_since = False, None
    trip_km, last_t, last_reset = 0.0, time.time(), None      # trip distance since this script started (see --distance)
    try:
        while True:
            time.sleep(0.1)
            o = read_out()
            d = bridge.latest() if bridge else None
            # ---- game -> bike: grade ----
            grade = 0.0
            if o and o["in_veh"]:
                if o["seq"] != last_seq:
                    hist.append(o["pitch"])
                    last_seq = o["seq"]
                if hist:
                    grade = statistics.median(hist)
            else:
                hist.clear()
            grade = max(a.min_grade, min(a.max_grade, grade * a.grade_scale))
            now = time.time()
            if o:                                          # trip-reset key in the game (Ctrl+Shift+O)
                if last_reset is not None and o["odo_resets"] != last_reset:
                    trip_km = 0.0
                last_reset = o["odo_resets"]
            dt = min(now - last_t, 0.5)
            last_t = now
            if bridge and not a.no_grade and (grade_sent is None or abs(grade - grade_sent) >= 0.1 or now - grade_t > 1.0) and now - grade_t >= 0.25:
                bridge.send({"grade": round(grade, 2)})
                grade_sent, grade_t = grade, now
            # ---- bike -> game: target speed ----
            if a.fake_kph is not None:
                target, rpm, watts, bike_kph = a.fake_kph, 0, 0, a.fake_kph
            elif d:
                bike_kph, rpm, watts = d.get("kph", 0.0), d.get("rpm", 0.0), d.get("watts", 0)
                # "pedalling" comes from cadence only (the bike's own speed keeps climbing on a downhill with no pedalling,
                # and must not release the game's handbrake). On at >= --pedal-rpm, off after rpm < half of it for 1 s.
                if rpm >= a.pedal_rpm:
                    pedalling, low_since = True, None
                elif pedalling and rpm < a.pedal_rpm / 2:
                    low_since = low_since or now
                    if now - low_since > 0.5:
                        pedalling = False
                else:
                    low_since = None
                target = min(bike_kph * a.speed_scale, a.max_kph) if pedalling else 0.0
            else:
                target = None      # no bike data: do not write; the mod goes stale and lets go
            if a.distance == "game":                       # the vehicle's real speed while you are on it
                if o and o["in_veh"]:
                    trip_km += max(0.0, o["speed"]) * dt / 3600.0
            elif d and pedalling:                          # pedalling: the bike's own speed
                trip_km += max(0.0, bike_kph) * dt / 3600.0
            elif d and o and o["in_veh"]:                  # coasting: the bike is still rolling in the game, so count that speed
                trip_km += max(0.0, o["speed"]) * dt / 3600.0
            if target is not None:
                seq += 1
                write_in(seq, target, rpm, watts, grade, (d or {}).get("kj", 0.0) or 0.0, a.hud_scale, a.units, 0.0 if grade < -2.0 else a.coast_brake, trip_km)
            row = [round(now - t0, 1), o["speed"] if o else "", o["pitch"] if o else "", round(grade, 2),
                   "" if target is None else round(target, 1), round(bike_kph, 1) if (d or a.fake_kph) else "",
                   round(rpm) if (d or a.fake_kph) else "", watts if (d or a.fake_kph) else "",
                   o["engaged"] if o else "", o["cruise_kmh"] if o else "", round(trip_km, 4), o["odo_resets"] if o else ""]
            log.writerow(row)
            logf.flush()           # keep the ride log intact even if the script is killed
            print(f"\rgame {row[1]!s:>6} km/h  grade {grade:+5.1f}%  target {row[4]!s:>5}  bike {row[5]!s:>5} km/h  rpm {row[6]!s:>4}  W {row[7]!s:>4}  engaged {row[8]!s}  ", end="", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            os.remove(IN)
        except OSError:
            pass
        print("\nstopped; in.xml removed so the game takes back control")


if __name__ == "__main__":
    main()
