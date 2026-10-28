"""Generates BikeMan's art with no imaging library: signed-distance shapes -> RGBA -> PNG + uncompressed 32-bit DDS.

    python3 tools/make_art.py mod/images        # hud_bg, hud_icon
    python3 tools/make_art.py mod/ --icon       # icon_BikeMan (256x256 mod icon)
"""
import math
import os
import struct
import sys
import zlib


def cov(d):
    """distance in pixels (negative inside) -> coverage 0..1"""
    return max(0.0, min(1.0, 0.5 - d))


def over(dst, col, a):
    """composite colour (r, g, b, alpha 0-255) at coverage a onto dst (r, g, b, alpha 0-255)"""
    sa = a * (col[3] / 255.0)
    da = dst[3] / 255.0
    oa = sa + da * (1 - sa)
    if oa <= 0:
        return dst
    return tuple((col[i] * sa + dst[i] * da * (1 - sa)) / oa for i in range(3)) + (oa * 255.0,)


def seg(px, py, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))


def save(w, h, pix, base):
    raw = b"".join(b"\0" + bytes(int(round(c)) for p in pix[y] for c in p) for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    open(base + ".png", "wb").write(png)
    bgra = b"".join(bytes((int(round(p[2])), int(round(p[1])), int(round(p[0])), int(round(p[3]))))
                    for row in pix for p in row)
    hdr = b"DDS " + struct.pack("<7I", 124, 0x100F, h, w, w * 4, 0, 0) + b"\0" * 44
    hdr += struct.pack("<8I", 32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    hdr += struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    open(base + ".dds", "wb").write(hdr + bgra)


# cyclist drawn on a 128 x 128 grid
LINES = [((30, 88), (58, 88), 5), ((58, 88), (48, 62), 5), ((48, 62), (86, 62), 5), ((58, 88), (86, 62), 5),
         ((86, 62), (98, 88), 5), ((86, 62), (92, 50), 5), ((88, 50), (100, 52), 5), ((48, 58), (74, 36), 9),
         ((74, 36), (94, 52), 5), ((48, 58), (66, 74), 8), ((66, 74), (58, 90), 7)]


def cyclist_cov(px, py):
    """coverage of the cyclist at a point given in 128-grid coordinates"""
    a = 0.0
    for cx in (30, 98):
        a = max(a, cov(abs(math.hypot(px - cx, py - 88) - 20) - 2.5))
    for p1, p2, w in LINES:
        a = max(a, cov(seg(px, py, p1, p2) - w / 2))
    return max(a, cov(math.hypot(px - 80, py - 24) - 9))


def make_hud(out):
    W, H, R, B = 680, 300, 36, 5          # panel is 340 x 150 design pixels at 2x
    pix = []
    for y in range(H):
        row = []
        for x in range(W):
            px, py = x + 0.5, y + 0.5
            qx, qy = abs(px - W / 2) - (W / 2 - R), abs(py - H / 2) - (H / 2 - R)
            d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - R
            p = (0, 0, 0, 0.0)
            p = over(p, (8, 10, 14, 170), cov(d))
            p = over(p, (235, 235, 235, 215), cov(abs(d + B / 2) - B / 2))
            if 22 < px < W - 22:
                p = over(p, (235, 235, 235, 110), cov(abs(py - 60) - 1.5))
            row.append(p)
        pix.append(row)
    save(W, H, pix, os.path.join(out, "hud_bg"))
    pix = [[(120, 215, 255, cyclist_cov(x + 0.5, y + 0.5) * 255) for x in range(128)] for y in range(128)]
    save(128, 128, pix, os.path.join(out, "hud_icon"))


def make_icon(out, name="icon_BikeMan"):
    S, R = 256, 40
    pix = []
    for y in range(S):
        row = []
        for x in range(S):
            px, py = x + 0.5, y + 0.5
            qx, qy = abs(px - S / 2) - (S / 2 - R), abs(py - S / 2) - (S / 2 - R)
            d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - R
            p = (0, 0, 0, 0.0)
            p = over(p, (18, 54, 90, 255), cov(d))
            p = over(p, (120, 215, 255, 255), cov(abs(d + 4) - 4) * 0.8)
            c = cyclist_cov((px - 28) / 1.55, (py - 36) / 1.55)       # centre the 128-grid figure in the tile
            p = over(p, (255, 255, 255, 255), c)
            row.append(p)
        pix.append(row)
    save(S, S, pix, os.path.join(out, name))


if __name__ == "__main__":
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    make_icon(out) if "--icon" in sys.argv else make_hud(out)
    print("ok")
