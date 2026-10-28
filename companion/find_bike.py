"""List nearby Bluetooth LE devices so you can find your bike's address.

Wake the bike by pedalling, close the Renpho app/Zwift, then run:
    py find_bike.py        (Windows)
    python3 find_bike.py   (Linux)
Bikes advertise the Fitness Machine service (FTMS, 0x1826); those are marked with *.
"""
import asyncio
from bleak import BleakScanner

FTMS = "00001826-0000-1000-8000-00805f9b34fb"


async def main():
    print("Scanning for 10 seconds ...")
    found = await BleakScanner.discover(timeout=10, return_adv=True)
    rows = []
    for addr, (dev, adv) in found.items():
        ftms = FTMS in [u.lower() for u in (adv.service_uuids or [])]
        rows.append((not ftms, -(adv.rssi or -999), addr, dev.name or adv.local_name or "(no name)", ftms))
    for _, _, addr, name, ftms in sorted(rows):
        print(f"{'*' if ftms else ' '} {addr}   {name}")
    print("\n* = advertises FTMS (a fitness machine). Use that address with --addr.")


asyncio.run(main())
