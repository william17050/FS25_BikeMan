# BikeMan (FS25 + smart bike) - repository context (v0.3, source of truth)

Goal: ride a Renpho RQ002 smart bike (Bluetooth FTMS) inside Farming Simulator 25 and release it publicly for **Windows and Linux** (no macOS). Windows AND Linux (Bazzite, Proton) are both verified working (see below). Keep the two platforms in sync. The user is on Bazzite (immutable Fedora, Steam/Proton). Read `README.md` for the full user-facing instructions.

## Repository layout
`mod/` is the FS25 mod source (BikeMan.lua, modDesc.xml, icon, images). `companion/` is bridge.py, fs25_link.py, find_bike.py and the start scripts (the "Parts" below refer to these). `tools/` has build_mod.sh, build_companion.sh and make_art.py. README.md is the user guide. v0.3 renamed the mod from FS25_BikeLink to FS25_BikeMan (Lua global, log tag `[BikeMan]`, settings folder `modSettings/FS25_BikeMan/`) and removed debug logging: the old FS25_BikeLink zip must NOT be installed alongside it. Build the mod with `tools/build_mod.sh` (files at the zip root).

## Parts
- `bridge.py`: owns the Bluetooth link (bleak) and serves JSON lines on `127.0.0.1:48765`. With no `--addr` it scans for a device advertising FTMS (0x1826) and uses the strongest signal. Needs `bleak` (the start script makes a `.venv`). The bike allows ONE connection: close the Renpho app and Zwift first.
- `fs25_link.py`: stdlib only. Reads the game's `out.txt`, sends grade to the bridge, writes `in.xml` (target km/h, HUD data, trip distance) for the mod. Auto-finds the FS25 profile; override with `--profile`.
- `FS25_BikeMan.zip`: the FS25 mod (Lua, v0.2). Keep it ZIPPED. It exchanges small files in `modSettings/FS25_BikeMan/`. The game's Lua cannot read files with io, only write; it reads through `loadXMLFile` (in.xml).
- `find_bike.py`: lists nearby BLE devices, marking FTMS ones with `*`.
- Start scripts: `windows_*.bat`, `linux_start_bridge.sh`, `linux_start_link.sh`, `find_bike.sh`. **The `.sh` files are NEW and have never been run on Linux.** They were written on Windows. Check line endings (must be LF), `chmod +x`, and that the `.venv` approach works on Bazzite.

## What was verified on Windows (do not redo)
Bleak installs, the bridge finds and connects to the bike, `[BikeMan] v0.2 loaded` in log.txt, the live `game ... km/h` line, HUD panel, pedalling moves the vehicle, bike auto-discovery, trip odometer (matched the ride log: 0.30 mi shown vs 0.296 mi logged), and the trip-reset key. No `BikeMan` errors in log.txt.

## What was verified on Linux (Bazzite, 2026-10-28)
Steps 1-8 all pass: `find_bike.sh` lists the bike with `*` (RQ002); `linux_start_bridge.sh` finds it and connects; log shows `[BikeMan] v0.2 loaded` with no errors; `linux_start_link.sh` runs; HUD, pedalling, handbrake latch/release all work; trip odometer matched (panel 0.25 mi vs 0.252 mi logged in `trip_km`); Left Ctrl+Left Shift+O reset it (`trip reset requested (1)` in log.txt, `odo_resets` column = 1).
Linux-specific lessons:
- Run the scripts in the real Bazzite HOST terminal. An agent/IDE terminal may be a container (e.g. "Claude-Box", Ubuntu): it has no `python3-venv`, no system D-Bus and therefore no BlueZ/Bluetooth.
- A failed venv setup used to leave a half-built `.venv` that later runs mistook for a good one. `find_bike.sh` and `linux_start_bridge.sh` now check `.venv/bin/python` and `import bleak`, delete a broken `.venv`, and print a hint to use the host terminal.
- The game log warns the HUD DDS images are "raw format" (performance only). Compress them before a public release (also shrinks the mod zip, currently ~0.9 MB).
- The old `~/Documents/RenphoHack` tools (hillclimber.py, bridge_client.py) use port 8765; the BikeMan bridge defaults to 48765 (`--port 48765`).

## Linux checklist, in order (all passed)
1. `python3 --version`; `bluetoothctl show` (adapter powered on).
2. `./find_bike.sh` (wake the bike by pedalling first): the bike should appear with `*`. Needs BlueZ via D-Bus; if bleak cannot reach it, say exactly what failed.
3. `./linux_start_bridge.sh`: expect `Found ... at ...` then `Bike connected.`
4. Mod in the game: find the profile (default tried: `~/.local/share/Steam/steamapps/compatdata/2300320/pfx/drive_c/users/steamuser/Documents/My Games/FarmingSimulator2025`; Flatpak Steam is NOT auto-detected, use `--profile`). Check `gameSettings.xml` for an active `modsDirectoryOverride`: the game loads mods from there instead of `mods/`.
5. `log.txt` shows `[BikeMan] v0.2 loaded`.
6. `./linux_start_link.sh`: a live `game ... km/h` line updates; the HUD panel appears above the speedometer; pedalling moves the vehicle.
7. Trip odometer (top right of the panel) counts; **Left Ctrl + Left Shift + O** zeroes it and shows `TRIP RESET` (the log shows `trip reset requested`). Reading keys uses `Input.isKeyPressed` in Lua; confirm it works under Proton.
8. Ride logs: `rides/fs25_link_*.csv` has `trip_km` and `odo_resets` columns, written every row. Compare the panel's trip distance (shown in miles first) with `trip_km`.

## Key facts and gotchas
- Grade comes from body pitch, not terrain (terrain is wrong on bridges). "Pedalling" = cadence >= 25 rpm (`--pedal-rpm`).
- Trip distance = bike speed while pedalling + vehicle speed while coasting (`--distance game` = always vehicle speed). It restarts from zero when the link starts.
- Handbrake latches when stopped with the bike idle; release by pedalling, throttle, or holding reverse 0.5 s.
- The mod only acts while `in.xml` keeps changing (stale > 2 s = lets go). Killing the link by force leaves a stale `in.xml`; harmless, the mod lets go.
- The game must be FULLY quit to reload mod changes. On the user's Windows PC the game hangs when quit normally, so they close it from the taskbar. Mod changes apply only after a full quit; link-script changes do not need a game restart.
- Default port 48765 was chosen because 8765 clashed with another program on the user's PC. Both start scripts have a `PORT` setting; both must match.
- The test bike vehicle is the third-party mod `FS25_Lizard_MountainBike` (SleutjesModding). Do NOT bundle it; the README links to it by name only.
- Watch for: Bluetooth/BlueZ permission errors, Flatpak sandboxing, an unreadable profile path, `.sh` files with CRLF endings, `bleak` failing to install in the venv, `BikeMan` ERROR lines in log.txt.

## When you change something
Keep `bridge.py`, `fs25_link.py`, the mod and the README identical across platforms. Any change to the Lua mod needs the zip rebuilt with the files at the zip ROOT (`BikeMan.lua`, `modDesc.xml`, `images/`) using forward slashes. Update `README.md` when behaviour changes, and report back to the user exactly what you ran and what you saw. Do not claim Linux works until steps 1 to 8 pass.
