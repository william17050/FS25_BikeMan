"""
Renpho bridge: owns the Bluetooth connection to the bike and serves it on localhost.

  python bridge.py                 start it (leave it running; Ctrl+C to stop)
  python bridge.py --cap 40        highest res the game may command (default 40 = display 20)

Your game / tool connects to 127.0.0.1:48765 (plain TCP, one JSON object per line).

Bridge -> client, about once a second:
  {"type":"data","t":354.2,"rpm":74.0,"watts":103,"res":27,"dial":13.5,"kj":12.4,
   "target":30,"override":false,"cap":40}
  (also {"type":"hello",...} on connect and {"type":"status","bike":true/false})

Client -> bridge:
  {"res": 30}          set resistance (0-80 scale, clamped to --cap, ramped gradually)
  {"hold": 2.0}        seconds the bridge ignores the game after a manual dial turn (0.5-60; resets when the client leaves)
  {"reset_kj": true}   zero the work counter

Safety:
  * Turning the dial by hand always wins. The bridge notices, stops commanding, and ignores the
    game for --hold seconds ("override": true in the data) so you are never fought.
  * If every client disconnects (game crash) or the bridge exits, resistance returns to --safe.
  * The bridge never touches the bike's resistance until a client sends a "res" command.

Close the Renpho app and Zwift first (the bike allows one Bluetooth connection).
"""
import argparse
import asyncio
import csv
import json
import os
import struct
import time
from datetime import datetime

from bleak import BleakClient, BleakScanner

ADDR_DEFAULT = None  # find the bike by scanning; override with --addr
PORT_DEFAULT = 48765
FTMS = "00001826-0000-1000-8000-00805f9b34fb"  # Fitness Machine service
IBD = "00002ad2-0000-1000-8000-00805f9b34fb"  # FTMS Indoor Bike Data
CP = "00002ad9-0000-1000-8000-00805f9b34fb"   # FTMS Control Point
VND = "00000004-21a4-11e8-8812-000c2920efff"  # vendor telemetry stream (~5 Hz, includes res)
MAX_RES = 80                                  # bike clamps here (display 40 = 40 N*m)


def parse_vendor(raw):
    """Vendor frame: SLIP-style (ends with 0xC0, escapes DB DC = C0, DB DD = DB). After unescaping:
    byte 3 = cadence rpm, bytes 6-7 = power x10, bytes 14 and 15 = res (equal in steady state).
    Returns {"res":..., "rpm":...} or None if the frame doesn't look right."""
    raw = bytes(raw)
    if not raw or raw[-1] != 0xC0:
        return None
    out, i, body = bytearray(), 0, raw[:-1]
    while i < len(body):
        c = body[i]
        if c == 0xDB and i + 1 < len(body):
            out.append(0xC0 if body[i + 1] == 0xDC else 0xDB if body[i + 1] == 0xDD else c)
            i += 2
        else:
            out.append(c)
            i += 1
    if len(out) < 16 or out[0] != 0x00 or out[1] != 0x50 or out[14] != out[15]:
        return None
    return {"res": out[14], "rpm": out[3]}


def parse_ibd(d):
    flags = struct.unpack_from("<H", d, 0)[0]
    i, out = 2, {}
    if not flags & 0x0001:
        out["kph"] = struct.unpack_from("<H", d, i)[0] * 0.01; i += 2   # the bike's own virtual speed
    if flags & 0x0002: i += 2
    if flags & 0x0004:
        out["rpm"] = struct.unpack_from("<H", d, i)[0] * 0.5; i += 2
    if flags & 0x0008: i += 2
    if flags & 0x0010: i += 3
    if flags & 0x0020:
        out["res"] = struct.unpack_from("<h", d, i)[0]; i += 2
    if flags & 0x0040:
        out["watts"] = struct.unpack_from("<h", d, i)[0]; i += 2
    return out


class Bridge:
    def __init__(self, args):
        self.a = args
        self.default_hold = args.hold
        self.click_mode = False    # game asked for dial clicks as events ({"clicks": true})
        self.fast_res = None       # res from the 5 Hz vendor stream
        self.fast_rpm = 0
        self.fast_t = 0.0
        self.t0 = time.time()
        self.client = None
        self.bike_ok = False
        self.has_control = False
        self.data = {"rpm": 0.0, "watts": 0, "res": None, "kph": 0.0}
        self.grade = None          # grade mode: hill grade in percent; the bike computes load, speed and gears itself
        self.grade_sent = None
        self.grade_t = 0.0
        self.kj = 0.0
        self.last_t = None
        self.commanded = None      # last res WE sent (None = we haven't, or the dial took over)
        self.t_cmd = 0.0
        self.target = None         # res the game wants; the ramp loop walks toward it
        self.override_until = 0.0
        self.writers = set()
        self.no_client_since = time.time()
        self.cmd_lock = asyncio.Lock()
        self.csv_file = None
        self.csv = None
        self.ev = None
        self.last_want = None
        if not args.no_log:
            folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rides")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"bridge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            self.csv_file = open(path, "w", newline="")
            self.csv = csv.writer(self.csv_file)
            self.csv.writerow(["t_sec", "rpm", "watts", "res", "kj", "override", "commanded", "target", "vendor_res", "kph", "grade"])
            self.ev = open(path.replace(".csv", "_events.txt"), "w")
            print(f"Logging rides to {path}")

    def log_ev(self, msg):
        if self.ev:
            self.ev.write(f"[{time.time() - self.t0:7.1f}] {msg}\n")
            self.ev.flush()

    # ---- helpers -------------------------------------------------------
    def overriding(self):
        return time.time() < self.override_until

    def snapshot(self):
        res = self.data["res"]
        return {"type": "data", "t": round(time.time() - self.t0, 1),
                "rpm": self.data["rpm"], "watts": self.data["watts"], "res": res,
                "dial": None if res is None else res / 2, "kj": round(self.kj, 2),
                "kph": self.data.get("kph", 0.0), "grade": self.grade,
                "target": self.target, "override": self.overriding(), "cap": self.a.cap}

    def broadcast(self, obj):
        line = (json.dumps(obj) + "\n").encode()
        for w in list(self.writers):
            if w.is_closing():
                self.writers.discard(w)
                continue
            try:
                w.write(line)
            except Exception:
                self.writers.discard(w)

    # ---- bike side -----------------------------------------------------
    def on_ibd(self, _, raw):
        try:
            v = parse_ibd(bytes(raw))
        except Exception:
            return
        now = time.time()
        self.data.update(v)
        w = self.data["watts"]
        if self.last_t is not None and w and w > 0:
            self.kj += w * min(now - self.last_t, 2.0) / 1000.0
        self.last_t = now
        res = self.data["res"]
        # Dial override: res drifted away from what we set, once things have settled.
        if (not self.click_mode and self.commanded is not None and res is not None and now - self.t_cmd > 2.0
                and abs(res - self.commanded) >= 2 and not self.overriding()):
            self.override_until = now + self.a.hold
            self.target = None
            self.commanded = None
            print(f"Manual dial change detected (res {res}). Ignoring the game for {self.a.hold:.0f} s.")
        snap = self.snapshot()
        self.broadcast(snap)
        if self.csv:
            self.csv.writerow([snap["t"], snap["rpm"], snap["watts"], snap["res"], snap["kj"], int(snap["override"]),
                               self.commanded, self.target, self.fast_res, snap["kph"], self.grade])
            self.csv_file.flush()

    def on_vendor(self, _, raw):
        try:
            v = parse_vendor(raw)
        except Exception:
            return
        if v:
            self.fast_res, self.fast_rpm, self.fast_t = v["res"], v["rpm"], time.time()

    def on_cp(self, _, raw):
        d = bytes(raw)
        if len(d) >= 3 and d[0] == 0x80 and d[2] != 1:
            print(f"Bike rejected op {d[1]:#04x} (result {d[2]})")
            if d[2] == 5:
                self.has_control = False

    async def ensure_control(self):
        if self.has_control:
            return
        await self.client.write_gatt_char(CP, bytes([0x00]), response=True)   # Request Control
        await asyncio.sleep(0.2)
        await self.client.write_gatt_char(CP, bytes([0x07]), response=True)   # Start/Resume
        self.has_control = True

    async def send_res(self, value):
        if not (self.client and self.bike_ok):
            return False
        value = max(0, min(MAX_RES, int(value)))
        async with self.cmd_lock:
            try:
                await self.ensure_control()
                await self.client.write_gatt_char(CP, bytes([0x04, value]), response=True)
            except Exception as e:
                print(f"Command failed: {e}")
                self.log_ev(f"COMMAND FAILED res {value}: {e}")
                self.has_control = False
                return False
        self.log_ev(f"sent res {value}")
        self.commanded = value
        self.t_cmd = time.time()
        return True

    async def send_grade(self, pct):
        """FTMS Set Indoor Bike Simulation Parameters: the bike works out resistance (and gears via its dial) itself."""
        if not (self.client and self.bike_ok):
            return False
        pct = max(-20.0, min(20.0, float(pct)))
        pkt = bytes([0x11]) + struct.pack("<hhBB", 0, int(round(pct * 100)), 40, 51)
        async with self.cmd_lock:
            try:
                await self.ensure_control()
                await self.client.write_gatt_char(CP, pkt, response=True)
            except Exception as e:
                print(f"Grade command failed: {e}")
                self.log_ev(f"GRADE FAILED {pct}: {e}")
                self.has_control = False
                return False
        self.log_ev(f"sent grade {pct:+.2f}%")
        self.grade_sent = pct
        self.grade_t = time.time()
        return True

    async def grade_loop(self):
        while True:
            await asyncio.sleep(0.25)
            if self.grade is None or not self.bike_ok:
                continue
            now = time.time()
            if self.grade_sent is None or abs(self.grade - self.grade_sent) >= 0.1 or now - self.grade_t > 3.0:
                await self.send_grade(self.grade)

    def detect_clicks(self):
        """Click mode: with the game holding control, each dial click moves the bike's res by +/-1.
        Whatever differs from what we last commanded, once the bike has had time to report our command, is
        dial clicks. Uses the 5 Hz vendor stream when it is flowing, else the 1 Hz FTMS data (slower settle).
        Ignored while not pedaling (the bike drifts its res by itself then) and for implausible jumps."""
        now = time.time()
        if now - self.fast_t < 0.6:
            res, rpm, settle = self.fast_res, self.fast_rpm, 0.8
        else:
            res, rpm, settle = self.data["res"], self.data["rpm"], 1.6
        if (not self.click_mode or self.commanded is None or res is None or not self.bike_ok
                or now - self.t_cmd < settle or res == self.commanded):
            return False
        n = res - self.commanded
        if rpm < 5 or abs(n) > 10:
            # not a dial click (idle drift or a command the bike hasn't taken): resync and let the game resend
            self.log_ev(f"RESYNC: bike res {res} vs commanded {self.commanded} (rpm {rpm}, diff {n:+d}) - not treated as clicks")
            self.commanded = res
            return False
        self.log_ev(f"CLICKS {n:+d}: bike res {res} vs commanded {self.commanded}")
        self.commanded = res        # accept it as the new baseline; the game answers with a new target
        self.target = None
        self.broadcast({"type": "clicks", "n": n})
        print(f"Dial clicks: {n:+d}")
        return True

    async def find_bike(self):
        """Scan for a bike advertising FTMS; with several, take the strongest signal."""
        print("Looking for a bike (wake it by pedalling) ...")
        found = await BleakScanner.discover(timeout=8, return_adv=True)
        bikes = [(adv.rssi or -999, dev.address, dev.name or adv.local_name or "(no name)")
                 for dev, adv in found.values()
                 if FTMS in [u.lower() for u in (adv.service_uuids or [])]]
        bikes.sort(reverse=True)
        if not bikes:
            print("No bike found yet. Wake it by pedalling and close the Renpho app and Zwift.")
            return None
        if len(bikes) > 1:
            print("Several fitness machines found; using the strongest. Use --addr to choose:")
            for rssi, addr, name in bikes:
                print(f"  {addr}  {name}  ({rssi} dBm)")
        print(f"Found {bikes[0][2]} at {bikes[0][1]}")
        return bikes[0][1]

    async def bike_loop(self):
        while True:
            gone = asyncio.Event()
            try:
                if not self.a.addr:
                    self.a.addr = await self.find_bike()
                    if not self.a.addr:
                        await asyncio.sleep(2)
                        continue
                print(f"Connecting to bike {self.a.addr} ...")
                async with BleakClient(self.a.addr, disconnected_callback=lambda _c: gone.set()) as c:
                    self.client = c
                    await c.start_notify(IBD, self.on_ibd)
                    await c.start_notify(CP, self.on_cp)
                    if getattr(self.a, "vendor", False):
                        try:
                            await c.start_notify(VND, self.on_vendor)
                            print("Vendor stream on.")
                        except Exception as e:
                            print(f"Vendor stream not available ({e}); using the slower FTMS data for dial clicks.")
                    self.bike_ok = True
                    self.has_control = False
                    print("Bike connected.")
                    self.broadcast({"type": "status", "bike": True})
                    while not gone.is_set():
                        await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Bike connection problem: {e}")
            self.bike_ok = False
            self.client = None
            self.has_control = False
            self.commanded = None
            self.broadcast({"type": "status", "bike": False})
            await asyncio.sleep(3)

    async def ramp_loop(self):
        """Walks resistance toward the game's target gradually, and falls back to --safe if the game is gone."""
        while True:
            await asyncio.sleep(0.5)
            if self.grade is not None:
                continue
            if self.detect_clicks():
                continue
            if (not self.writers and self.commanded is not None and not self.overriding()
                    and time.time() - self.no_client_since > 5 and self.target != self.a.safe):
                print(f"No game connected: returning resistance to {self.a.safe}.")
                self.target = self.a.safe
            if self.overriding() or self.target is None or not self.bike_ok:
                continue
            base = self.commanded if self.commanded is not None else self.data["res"]
            if base is None or base == self.target:
                continue
            delta = self.target - base
            if self.click_mode:
                step = delta        # one jump: a ramp of small steps could overwrite a dial click mid-way
            else:
                step = min(delta, self.a.ramp_up) if delta > 0 else max(delta, -self.a.ramp_down)
            await self.send_res(base + step)

    async def shutdown(self):
        if self.bike_ok and self.grade is not None:
            self.grade = None
            print(f"Leaving simulation mode: resistance back to {self.a.safe} ...")
            await self.send_res(self.a.safe)
        elif self.bike_ok and self.commanded is not None and not self.overriding():
            print(f"Restoring resistance to {self.a.safe} ...")
            await self.send_res(self.a.safe)
        if self.csv_file:
            self.csv_file.close()
        if self.ev:
            self.ev.close()

    # ---- client side ---------------------------------------------------
    def handle_cmd(self, msg):
        if "grade" in msg:
            try:
                g = max(-20.0, min(20.0, float(msg["grade"])))
            except Exception:
                return {"type": "error", "msg": "grade must be a number"}
            if self.grade is None:
                self.log_ev("entering grade (simulation) mode")
                self.target = None
                self.commanded = None
            self.grade = g
            return {"type": "ack", "grade": g}
        if "res" in msg:
            if self.grade is not None:
                return {"type": "ack", "applied": False, "reason": "grade mode"}
            if self.overriding():
                return {"type": "ack", "applied": False, "reason": "manual override", "override": True}
            try:
                want = int(round(float(msg["res"])))
            except Exception:
                return {"type": "error", "msg": "res must be a number"}
            want = max(0, min(self.a.cap, want))
            if want != self.last_want:
                self.log_ev(f"game asked for res {want}")
                self.last_want = want
            self.target = want
            return {"type": "ack", "applied": True, "target": want}
        if "clicks" in msg:
            self.click_mode = bool(msg["clicks"])
            return {"type": "ack", "clicks": self.click_mode}
        if "hold" in msg:
            try:
                self.a.hold = max(0.5, min(60.0, float(msg["hold"])))
            except Exception:
                return {"type": "error", "msg": "hold must be a number"}
            return {"type": "ack", "hold": self.a.hold}
        if msg.get("reset_kj"):
            self.kj = 0.0
            return {"type": "ack", "kj": 0}
        return {"type": "error", "msg": "unknown command"}

    async def handle_client(self, reader, writer):
        self.writers.add(writer)
        hello = {"type": "hello", "cap": self.a.cap, "max": MAX_RES, "bike": self.bike_ok}
        writer.write((json.dumps(hello) + "\n").encode())
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                    resp = self.handle_cmd(msg) if isinstance(msg, dict) else {"type": "error", "msg": "expected an object"}
                except Exception:
                    resp = {"type": "error", "msg": "bad json"}
                writer.write((json.dumps(resp) + "\n").encode())
        except Exception:
            pass
        finally:
            self.writers.discard(writer)
            if not self.writers:
                self.no_client_since = time.time()
                self.a.hold = self.default_hold
                self.click_mode = False
                if self.grade is not None:      # game gone: leave simulation mode so the bike is not stuck on a hill
                    self.grade = None
                    self.grade_sent = None
                    asyncio.get_event_loop().create_task(self.send_res(self.a.safe))
            try:
                writer.close()
            except Exception:
                pass


async def run(args):
    b = Bridge(args)
    server = await asyncio.start_server(b.handle_client, "127.0.0.1", args.port)
    print(f"Bridge listening on 127.0.0.1:{args.port}   cap res {args.cap}, safe res {args.safe}. Ctrl+C to stop.")
    tasks = [asyncio.create_task(b.bike_loop()), asyncio.create_task(b.ramp_loop()), asyncio.create_task(b.grade_loop())]
    try:
        async with server:
            await server.serve_forever()
    finally:
        await b.shutdown()          # before the bike task is cancelled, so the restore can still be sent
        for t in tasks:
            t.cancel()


def main():
    p = argparse.ArgumentParser(description="Renpho bike bridge")
    p.add_argument("--addr", default=ADDR_DEFAULT, help="bike Bluetooth address; omit to find it automatically")
    p.add_argument("--port", type=int, default=PORT_DEFAULT)
    p.add_argument("--cap", type=int, default=40, help="highest res a game may command (hard max 80)")
    p.add_argument("--safe", type=int, default=20, help="res to return to when the game disconnects or the bridge exits")
    p.add_argument("--hold", type=float, default=15, help="seconds to ignore the game after a manual dial move")
    p.add_argument("--ramp-up", type=int, default=4, help="max res increase per 0.5 s")
    p.add_argument("--ramp-down", type=int, default=8, help="max res decrease per 0.5 s")
    p.add_argument("--no-log", action="store_true", help="don't write a CSV of the ride")
    p.add_argument("--vendor", action="store_true",
                   help="also listen to the bike's 5 Hz vendor stream (experimental: the bike stopped obeying load commands with it on)")
    args = p.parse_args()
    args.cap = max(0, min(MAX_RES, args.cap))
    args.safe = max(0, min(args.cap, args.safe))
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nBridge stopped.")


if __name__ == "__main__":
    main()
