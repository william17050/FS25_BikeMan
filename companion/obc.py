"""
OpenBikeControl (OBC) handlebar controllers for the bridge: buttons on the bars steer, brake and change the hill feel.

  python bridge.py --obc                      find a controller over Bluetooth (it advertises the OBC service)
  python bridge.py --obc AA:BB:CC:DD:EE:FF    that controller over Bluetooth
  python bridge.py --obc 192.168.1.20:36866   that controller over the network (e.g. the BikeControl app), IP:port

Button -> what it does (the bridge sends these to fs25_link.py, which puts them in in.xml for the mod):
  Steer Left / Steer Right   steer while held                     Steering Angle   steer proportionally (30 deg = full lock)
  Brake                      brake while held (analog strength)   Lap              zero the trip distance
  Shift Up / Increase Difficulty    hills harder (--grade-scale +0.1)
  Shift Down / Decrease Difficulty  hills easier (--grade-scale -0.1)
One physical press may carry several button IDs (e.g. Shift Up + Increase Difficulty + Select): only the first one in
PRIORITY that we support acts, once. The others in that message are ignored until they are released.
Protocol: https://github.com/OpenBikeControl/openbikecontrol-protocol
"""
import ipaddress
import re

SERVICE = "d273f680-d548-419d-b9d1-fa0472345229"     # advertised by every OBC controller
BUTTONS = "d273f681-d548-419d-b9d1-fa0472345229"     # button state (notify)
APP_INFO = "d273f683-d548-419d-b9d1-fa0472345229"    # app information (write)
APP_ID = "bikeman"
APP_VERSION = "0.3"
MSG_BUTTONS, MSG_STATUS, MSG_HAPTIC, MSG_APP_INFO = 0x01, 0x02, 0x03, 0x04

SHIFT_UP, SHIFT_DOWN = 0x01, 0x02
STEER_LEFT, STEER_RIGHT, BRAKE, ANGLE = 0x18, 0x19, 0x1A, 0x1B
HARDER, EASIER, LAP = 0x30, 0x31, 0x35
STEER_FULL_DEG = 30.0                                # handlebar angle that means full lock

# Press actions, most important first. Steer and brake are held; the rest fire once per press.
PRIORITY = [BRAKE, SHIFT_UP, SHIFT_DOWN, HARDER, EASIER, STEER_LEFT, STEER_RIGHT, LAP]
ACTION = {BRAKE: "brake", SHIFT_UP: "grade_up", SHIFT_DOWN: "grade_down", HARDER: "grade_up", EASIER: "grade_down",
          STEER_LEFT: "steer_left", STEER_RIGHT: "steer_right", LAP: "trip_reset"}
SUPPORTED = PRIORITY + [ANGLE]

_MAC = re.compile(r"[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}")
_UUID = re.compile(r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}")


def parse_target(text):
    """--obc value -> ("ble", None) to scan, ("ble", address) or ("tcp", (ip, port)). Raises ValueError for anything else."""
    text = (text or "").strip()
    if text in ("", "auto"):
        return "ble", None
    if _MAC.fullmatch(text) or _UUID.fullmatch(text):
        return "ble", text
    host, sep, port = text.rpartition(":")
    if sep and port.isdigit() and 1 <= int(port) <= 65535:
        try:
            return "tcp", (str(ipaddress.ip_address(host.strip("[]"))), int(port))
        except ValueError:
            pass
    raise ValueError(f"--obc expects 'auto', a Bluetooth address or IP:port, not {text!r}")


def parse_buttons(data):
    """[0x01, id1, state1, id2, state2, ...] -> [(id, state), ...]; [] for any other message."""
    data = bytes(data)
    if len(data) < 3 or data[0] != MSG_BUTTONS:
        return []
    return [(data[i], data[i + 1]) for i in range(1, len(data) - 1, 2)]


def split_tcp(data):
    """Split one TCP read into messages. Button state has no length field, so it runs to the end of the read."""
    out, i = [], 0
    while i < len(data):
        t = data[i]
        if t == MSG_STATUS:
            i += 3
        elif t == MSG_HAPTIC:
            i += 4
        elif t == MSG_BUTTONS:
            out.append(bytes(data[i:]))
            break
        else:
            break
    return out


def app_info():
    """App Information message, sent right after connecting: who we are and which button IDs we act on."""
    app_id, ver = APP_ID.encode(), APP_VERSION.encode()
    return bytes([MSG_APP_INFO, 0x01, len(app_id)]) + app_id + bytes([len(ver)]) + ver + bytes([len(SUPPORTED)] + SUPPORTED)


class Mapper:
    """Turns OBC button messages into BikeMan controls. handle() returns the one-shot actions to run (0 or 1 of them)
    and keeps steer (-1 left .. 1 right) and brake (0..1) up to date for the held ones."""

    def __init__(self):
        self.down = set()          # IDs currently pressed (supported or not)
        self.held = None           # the held press that won (BRAKE, STEER_LEFT or STEER_RIGHT), or None
        self.brake_level = 1.0
        self.angle = None          # from Steering Angle in -1..1; None = the controller reports no angle

    def state(self):
        steer = self.angle
        if steer is None:
            steer = -1.0 if self.held == STEER_LEFT else 1.0 if self.held == STEER_RIGHT else 0.0
        return {"steer": round(steer, 3), "brake": round(self.brake_level if self.held == BRAKE else 0.0, 2)}

    @staticmethod
    def _brake(v):
        """0x01 = full, 0x02-0xC9 = value - 1 percent (above 100% is clamped)."""
        return 1.0 if v == 0x01 else min(v - 1, 100) / 100.0

    def handle(self, data):
        fresh = []
        for bid, v in parse_buttons(data):
            if bid == ANGLE:
                if v == 0x00:
                    self.angle = None              # not calibrated / lost: Steer Left / Right buttons work again
                elif v not in (0x01, 0xFF):
                    self.angle = max(-1.0, min(1.0, (v - 0x80) * 0.5 / STEER_FULL_DEG))
                continue
            if v == 0x00:
                self.down.discard(bid)
                if bid == self.held:
                    self.held = None
                continue
            if bid == BRAKE and bid == self.held:
                self.brake_level = self._brake(v)  # analog brake moving while held
            if bid in self.down:
                continue
            self.down.add(bid)
            if bid in ACTION and not (bid in (STEER_LEFT, STEER_RIGHT) and self.angle is not None):
                fresh.append((bid, v))
        if not fresh:
            return []
        bid, v = min(fresh, key=lambda p: PRIORITY.index(p[0]))
        if bid in (BRAKE, STEER_LEFT, STEER_RIGHT):
            self.held = bid
            if bid == BRAKE:
                self.brake_level = self._brake(v)
            return []
        return [ACTION[bid]]

    def release_all(self):
        """Controller gone: nothing stays pressed."""
        self.down.clear()
        self.held = None
        self.angle = None
