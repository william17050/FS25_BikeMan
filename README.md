# BikeMan: ride a smart bike inside Farming Simulator 25

Pedal a Bluetooth smart bike (FTMS) and drive a vehicle in FS25 with it. Your cadence and speed move the vehicle. The slope the vehicle is on is sent back to the bike as resistance. An in-game panel shows your live bike stats.

**Unofficial.** Not affiliated with GIANTS Software, Renpho or any other company. Developed and tested with a Renpho RQ002 and the free **Lizard Mountain Bike** mod. Works on **Windows** and **Linux** (Steam/Proton). macOS is not supported.

## Downloads

Two files from the **Releases** page (or build them yourself, see below):

- **`FS25_BikeMan.zip`**: the game mod. Goes in your FS25 `mods` folder. Keep it zipped.
- **`BikeMan_Companion.zip`**: the program that talks to the bike. Unzip it anywhere. It holds the `companion` folder with the start scripts used in this guide.

## Safety

BikeMan sends resistance commands to your exercise bike. Keep the resistance cap (`--cap`) at a level you are comfortable with, stay seated on the bike while it is running, and stop if anything feels wrong. You can always turn the bike's own dial by hand: the bridge then stops commanding for a while. Use at your own risk, see the licence.

---

## 1. How it fits together

```
 Smart bike  --Bluetooth-->  bridge.py  --localhost:48765-->  fs25_link.py  --files-->  FS25 + BikeMan mod
 (FTMS)                      (owns the BT link)              (the go-between)          (moves the vehicle)
```

| Part | What it does |
|---|---|
| `bridge.py` | Holds the Bluetooth connection to the bike and shares it on `127.0.0.1` (this PC only). Needs the Python package `bleak`. |
| `fs25_link.py` | Reads what the game writes (`out.txt`), tells the bridge the slope, and writes `in.xml` with the target speed and HUD data. Uses only Python's standard library. |
| `FS25_BikeMan.zip` | The FS25 mod (separate download). **Keep it zipped.** It exchanges small files in `modSettings\FS25_BikeMan\`. |
| `find_bike.py` | Lists nearby Bluetooth devices so you can find your bike's address. |

Nothing here talks to the internet. The only network use is the localhost link between the two scripts.

---

## 2. What you need

- A Bluetooth LE smart bike or trainer that supports the standard **FTMS** profile with resistance control. Only the Renpho RQ002 has been tested. Others may work but are unverified.
- A PC with working Bluetooth (built-in or a USB dongle).
- **Python 3.11 or newer.**
- Farming Simulator 25 (Steam).
- A rideable vehicle mod. The tested one is **FS25_Lizard_MountainBike** (by SleutjesModding). It is a separate third-party mod and is not included here. Download it from its own page or ModHub.

**The bike only allows one Bluetooth connection.** Close the Renpho app, Zwift and anything else that talks to the bike before you start.

---

## 3. Windows setup

### 3.1 One-time

1. **Install Python** from python.org. In the installer, tick **Add python.exe to PATH** and keep the **py launcher** ticked.
2. **Find your FS25 mods folder.**
   - Normally: `Documents\My Games\FarmingSimulator2025\mods`. If your Documents folder is on OneDrive, use that one (`OneDrive\Documents\...`).
   - **Check for a custom mods folder.** If you have ever moved your mods, open `Documents\My Games\FarmingSimulator2025\gameSettings.xml` and look for a line like `<modsDirectoryOverride active="true" directory="D:\MyMods/"/>`. If it is active, that folder is where the game loads mods from, so use it instead.
3. **Copy `FS25_BikeMan.zip` into that mods folder. Do not unzip it.** Also put the Lizard Mountain Bike zip there.
4. **Bike address (optional).** The bridge finds your bike automatically by scanning for a fitness machine. You only need to set the address if you have more than one smart bike or trainer nearby:
   - Wake the bike by pedalling, and close the Renpho app and Zwift.
   - Double-click `windows_find_bike.bat`. Your bike appears with a `*` (it advertises FTMS). Copy its address.
   - Open `windows_start_bridge.bat` in Notepad and put it in `set "BIKE_ADDR=..."`. Save.

### 3.2 Each ride

1. Close the Renpho app and Zwift. Wake the bike by pedalling.
2. Double-click **`windows_start_bridge.bat`**. Leave the window open. The first run installs `bleak`. Wait for `Bike connected.`
3. Start FS25, load your savegame and make sure **BikeMan** and your bike vehicle are enabled for the save.
4. Get on the bike vehicle.
5. Double-click **`windows_start_link.bat`**. You should see a line like `game 0.0 km/h  grade -0.6%  target 0.0  bike 0.0 km/h  rpm 0 ...` updating.
6. Start pedalling.

Stop with Ctrl+C in each window (the link first). When the link stops it removes `in.xml`, and the game takes the vehicle back.

---

## 4. Linux setup (Steam / Proton, e.g. Bazzite, SteamOS, Fedora, Ubuntu)

### 4.1 One-time

1. **Check you have Python 3 and Bluetooth (BlueZ).** Both are present by default on Bazzite and SteamOS. Test with:
   ```bash
   python3 --version
   bluetoothctl show
   ```
   Your Bluetooth adapter must be powered on.
2. **Find your FS25 profile folder.** For native Steam with Proton it is normally:
   ```
   ~/.local/share/Steam/steamapps/compatdata/2300320/pfx/drive_c/users/steamuser/Documents/My Games/FarmingSimulator2025
   ```
   The scripts look there automatically. **If you use Flatpak Steam, or Steam is installed somewhere else, the scripts will not find it.** In that case set `EXTRA=(--profile "/full/path/to/FarmingSimulator2025")` in `linux_start_link.sh`. The Flatpak location is under `~/.var/app/com.valvesoftware.Steam/`.
3. **Copy `FS25_BikeMan.zip` into the `mods` folder inside that profile. Do not unzip it.** Also put the Lizard Mountain Bike zip there. Check `gameSettings.xml` in the profile for an active `modsDirectoryOverride`. If there is one, use that folder.
4. **Make the scripts runnable:**
   ```bash
   chmod +x linux_start_bridge.sh linux_start_link.sh find_bike.sh
   ```
5. **Bike address (optional).** The bridge finds your bike automatically. Set the address only if several smart bikes or trainers are nearby. Wake the bike by pedalling, close the Renpho app, and run:
   ```bash
   ./find_bike.sh
   ```
   Your bike appears with a `*`. Put its address in `BIKE_ADDR=""` at the top of `linux_start_bridge.sh`.

The first run of `linux_start_bridge.sh` or `find_bike.sh` creates a `.venv` folder next to the scripts and installs `bleak` into it. This avoids touching the system Python, which matters on immutable distros such as Bazzite.

### 4.2 Each ride

1. Close the Renpho app. Wake the bike by pedalling.
2. In a terminal: `./linux_start_bridge.sh`. Leave it open and wait for `Bike connected.`
3. Start FS25 from Steam, load the save, enable **BikeMan** and your bike vehicle, and get on it.
4. In a second terminal: `./linux_start_link.sh`.
5. Pedal.

---

## 5. How it behaves

- **Pedalling** means cadence of at least 25 rpm (`--pedal-rpm`). Your speed sets the vehicle's target speed.
- **Slope** comes from the vehicle's body pitch, not the terrain, because terrain is wrong on bridges. It is sent to the bike as resistance, scaled by `--grade-scale` and capped by `--cap`.
- **Stopping:** the handbrake latches when you are stopped and not pedalling. Release it by pedalling, using the throttle, or holding reverse for half a second.
- **Coasting:** when you stop pedalling while rolling, a gentle brake is applied (`--coast-brake`). It switches off on steep downhills.
- **Safety:** the mod only acts while `in.xml` keeps changing. If the link stops or freezes for more than 2 seconds, the mod lets go and you drive normally. The bridge returns the bike to a safe resistance when the game disconnects or the bridge exits.
- **Trip distance:** the top right of the in-game panel shows how far you have ridden since you started `fs25_link.py`, in miles, kilometres or both (follows `--units`). By default it works like a real bike computer: your **bike's own speed** is added up while you pedal, and the **vehicle's speed** while you coast, so rolling downhill counts. Use `--distance game` to always use the vehicle's speed instead (this follows `--speed-scale`). It restarts from zero each time you start the link. **To zero it during a ride, press Left Ctrl + Left Shift + O** in the game. The panel briefly shows `TRIP RESET`. The key is fixed in the mod and is not shown in the game's controls menu.
- **Ride logs:** the bridge writes a CSV of every ride into a `rides` folder next to the scripts. Use `--no-log` to turn it off.

---

## 6. Options

Set these in the start scripts. They are the same on both systems.

**`fs25_link.py`**

| Option | Default | Meaning |
|---|---|---|
| `--units both\|mph\|kmh` | `both` | Speed units on the in-game panel |
| `--hud-scale N` | `1.2` | Panel size (1 small, 2 large, 3 huge). Applies on restart of the link, not the game |
| `--grade-scale N` | `0.6` | How strongly slope affects resistance |
| `--min-grade` / `--max-grade` | `-10` / `20` | Slope limits in percent |
| `--distance bike\|game` | `bike` | Trip distance source: `bike` = bike speed while pedalling plus vehicle speed while coasting; `game` = always the vehicle speed |
| `--no-grade` | off | Do not send slope to the bike |
| `--speed-scale N` | `1.0` | Multiplier on your bike speed in the game |
| `--max-kph N` | `45` | Cap on game speed |
| `--pedal-rpm N` | `25` | Cadence that counts as pedalling |
| `--coast-brake 0..1` | `0.7` | Braking while rolling and not pedalling (0 = free coast) |
| `--profile PATH` | auto | FS25 profile folder if not found automatically |
| `--port N` | `48765` | Must match the bridge |
| `--fake-kph N` | off | Test without the bike: hold this speed in the game |

**`bridge.py`**

| Option | Default | Meaning |
|---|---|---|
| `--addr XX:XX:...` | automatic | Your bike's Bluetooth address. Without it, the bridge scans for a fitness machine and uses the strongest signal |
| `--cap N` | `40` (scripts use 50) | Highest resistance the game may command (hard max 80) |
| `--safe N` | `20` | Resistance to return to when the game disconnects |
| `--hold SECONDS` | `15` | Ignore the game for this long after you turn the bike's dial by hand |
| `--ramp-up` / `--ramp-down` | `4` / `8` | Max resistance change per half second |
| `--port N` | `48765` | Must match the link |
| `--no-log` | off | Do not write a ride CSV |

**Port already in use?** If the bridge fails with `only one usage of each socket address`, another program is using 48765. Change `PORT` in **both** start scripts to something else, for example `48766`.

---

## 7. Troubleshooting

**Linux: "ensurepip is not available" / "No module named bleak" / no Bluetooth.** You are probably in a container terminal (for example a dev-box or an IDE terminal). Run the scripts in your normal host terminal (Konsole on Bazzite). The scripts rebuild a broken `.venv` automatically on the next run.


**Check these first, in order.** Each one is a stage of the chain.

| Stage | What you should see | If not |
|---|---|---|
| Bluetooth bridge | `Bike connected.` | See 7.1 |
| Mod loaded | `[BikeMan] v0.3 loaded` in the game's `log.txt` | See 7.2 |
| Link running | A live `game ... km/h` line | See 7.3 |
| Pedalling | `rpm` and `W` rise, and the vehicle moves | See 7.4 |

`log.txt` is in the FS25 profile folder. Search for `BikeMan`.

### 7.1 The bridge will not connect
- Wake the bike by pedalling. It sleeps after a short idle.
- Close the Renpho app, Zwift and any other app using the bike. Only one connection is allowed.
- `No bike found yet` repeating: the bike is asleep or not advertising FTMS. Pedal, and run `find_bike.py` to see what is visible. With several devices nearby, set `BIKE_ADDR`.
- Wrong address: check `BIKE_ADDR`, or clear it to use automatic discovery.
- **Windows:** Bluetooth must be on. Check Settings, Bluetooth & devices. The tested setup did not need any pairing step in Windows settings.
- **Linux:** make sure the adapter is on (`bluetoothctl power on`) and BlueZ is running (`systemctl status bluetooth`).
- `bleak` install fails: update Python. 3.11 and newer are tested; 3.14 works on Windows.
- Antivirus blocking Python: allow it.

### 7.2 The mod does not load
- The zip must be in the mods folder the game actually uses (see the `modsDirectoryOverride` note). The game shows `Available mod ... FS25_BikeMan` in `log.txt` if it sees it.
- The zip must stay zipped, and the file name must be exactly `FS25_BikeMan.zip`.
- Enable **BikeMan** in the savegame's mod list.
- Mod changes only load after you fully quit the game.

### 7.3 The link prints nothing or cannot find the profile
- The game must be running with you on a vehicle.
- If you see `Could not find the FS25 profile folder`, add `--profile "<path>"` (see the Windows and Linux sections).
- If the bike numbers stay at zero, start the bridge first and check that both scripts use the same port.

### 7.4 The vehicle does not move
- The vehicle must be the bike. The mod acts on the vehicle you are in.
- Check `rpm` is above 25 in the link output.
- Look for `BikeMan` `ERROR` lines in `log.txt` and report them.
- If the handbrake is latched, pedal harder or hold reverse briefly.

### 7.5 Other
- **Resistance feels too hard or too easy:** lower `--cap` or `--grade-scale`, or turn the bike's dial by hand (the bridge then ignores the game for `--hold` seconds).
- **HUD too small or large:** change `--hud-scale`, then restart the link only.

---

## 8. Credits and notes

- Bike vehicle: **FS25_Lizard_MountainBike** by SleutjesModding. Not bundled; obtain it from its own page.
- Windows and Linux are supported. macOS is not.
- This is an early release (v0.3). Please report problems with the text from both script windows and the `BikeMan` lines from `log.txt`.

## 9. Building from source

```
git clone <this repository>
tools/build_mod.sh          # -> dist/FS25_BikeMan.zip
tools/build_companion.sh    # -> dist/BikeMan_Companion.zip
python3 tools/make_art.py mod/images           # regenerate the panel images
python3 tools/make_art.py mod --icon           # regenerate the mod icon
```

Layout: `mod/` (game mod: Lua, images, modDesc), `companion/` (Python bridge and link, start scripts), `tools/`.

## 10. Licence

MIT, see `LICENSE`. The Lizard Mountain Bike mod is by SleutjesModding and is not part of this project.
