# S-Bike Training Hub

**Turn a budget smart bike into a full training setup: offline 3D routes, virtual hills and gears, auto-shifting, ERG workouts, a phone handlebar remote, and fitness tracking. It runs entirely on your Mac, with no subscription and no cloud.**

It was built for, and has only been tested on, the **Merach S29**. Other smart bikes that speak Bluetooth FTMS may work, but we couldn't test them (see [Other bikes](#other-bikes)).

<p align="center">
  <img src="docs/ride-view.png" width="300" alt="The 3D ride view on Alpe d'Huez: speed, watts, cadence, grade, gear, a ghost race and the climb profile, with big shift buttons">
  &nbsp;
  <img src="docs/ride-post.png" width="380" alt="An automatic ride-post infographic with records, milestones, a power chart and time in zones">
</p>

## What it does

The S29 only accepts **one** Bluetooth connection, and it ignores the "hill" commands that training apps send. The hub sits in the middle: it holds the single connection to the bike, and then:

- **Shares the bike.** It re-advertises the bike as a new device ("SBike Hub"), so a watch (power + cadence) and a training app can connect at the same time.
- **Makes hills real.** Grades from a route or a training app become resistance, eased in smoothly, with **virtual gears** on top.
- **Auto-shifts.** It keeps your cadence in a band (65–80 rpm by default), shifting sooner the harder you spin. A **climbing mode** handles low-cadence standing efforts.
- **Computes virtual speed** from watts, weight and grade, so climbs feel like climbs.
- **Runs ERG workouts.** It holds a target wattage whatever your cadence.

On top of that:

| | |
|---|---|
| 🗺 **Offline routes in 3D** | Plan A→B rides, loops, or "N km in any direction" rides on real roads, with a local BRouter route planner. Search towns and mountains offline, or tap famous rides (Alpe d'Huez, Ventoux, Tourmalet, PCH…). Then ride them in a tilted 3D follow view with real terrain and buildings. You can import GPX from Strava, Komoot and others. |
| 📱 **Phone / tablet handlebar remote** | The ride view works on any phone or tablet on your Wi-Fi: giant shift buttons with vibration, a drawer for auto-shift, climbing mode, ERG and workouts. Pair by scanning a QR code on the Mac (a one-time code) or typing a PIN. |
| 👻 **Ghost racing** | Race your last ride on the same route: "14 s ahead". |
| 🧭 **Coach** | A 6-minute **morning diagnostic** (fixed watts, heart rate read off your watch) gives a go / easy / rest verdict against your own normal. The **timed-workout builder** lets you pick a length, drag bars, and see the parts rebalance in proportion. |
| 🎯 **Workout adherence** | Each part of a workout is graded A–F on how well you held it, shown as a pie and a radar chart in the ride report. |
| 📈 **Live graph, calories, fitness** | A live power graph in zone colors, calories from real work (kJ), personal bests (5 s / 1 / 5 / 20 min) with callouts, and a power-based fitness / fatigue / form chart. |
| 🏆 **Streaks & milestones** | Day and week streaks, tiered milestones, and fun comparisons (Eiffel Tower, Alpe d'Huez, Everest…). |
| 📣 **Ride posts** | An automatic, friendly-but-competitive infographic and caption for every ride, plus a "Copy for Claude" pack for custom ones. Optional Strava posting of the title and caption. |
| 🛠 **Workout builder** | Steady, ramp and interval blocks in % of FTP, so workouts rescale when your FTP changes. There's also an FTP ramp test. |
| 💪 **Self-healing** | If the bridge crashes mid-ride, the menu-bar icon restarts it and the ride continues in the same file. |

<p align="center">
  <img src="docs/planner.jpg" width="760" alt="The route planner: offline map with labels and hillshade, place search, and famous-ride ideas">
</p>
<p align="center">
  <img src="docs/coach.png" width="480" alt="The Coach page: morning diagnostic and the timed-workout builder with draggable bars and a pie chart">
  &nbsp;
  <img src="docs/adherence.png" width="340" alt="Workout adherence: planned parts as a pie, and a radar chart of how well each part was held">
</p>

## What you need

- **A Mac** with Bluetooth, running macOS 13 or newer. The hub uses Apple's Bluetooth and drawing libraries, so it's macOS-only.
- **Python 3.11+** (`brew install python`) and, for the route planner, **Java** (`brew install openjdk`).
- **A smart bike.** Tested: Merach S29.
- **Disk space for maps:** roughly 1–10 GB depending on the regions you choose. The bridge alone needs almost nothing.
- **Optional:** a watch that pairs with Bluetooth power/cadence sensors (tested: COROS Pace 4), and a phone or tablet for the handlebar remote.

## Quick start

```bash
git clone https://github.com/JHarp199345/S-Bike-Training-Hub.git
cd S-Bike-Training-Hub
./setup.sh
```

`setup.sh` does the following:
- creates the Python environment and installs the packages
- downloads the route planner, the map and the 3D terrain for the regions in [`regions.json`](regions.json), asking before each big download
- makes a **"S-Bike Hub" launcher on your Desktop**
- can add the 🚲 **menu-bar icon**

To skip maps and routes and get just the bridge, run `./setup.sh --no-maps`.

Then:

1. **Wake the bike** (pedal a few turns). Make sure no phone or app is connected to it.
2. **Double-click "S-Bike Hub" on your Desktop**, or use the 🚲 menu icon. The first time, macOS asks to allow **Terminal** to use Bluetooth; say yes. The control panel opens at <http://127.0.0.1:8729>.
3. **Pair your watch** to "SBike Hub" as a power meter and a speed/cadence sensor.
4. **Set yourself up:**
   - run the **FTP ramp test** from the panel. The starting FTP is only a guess, and zones, workouts and fitness all scale from it.
   - set your weight, which is used for virtual speed: create or edit `profile.json` in the project folder with `{"weight_kg": 80}` (your kg). Your FTP gets saved in the same file.
   - in the planner, move the map to where you ride and press **📍 Home view**.
5. **Put your phone on the handlebars.** Scan the QR code in the panel's *Phone remote* box (same Wi-Fi), and it opens the ride view, paired.

### Choosing map regions

Edit [`regions.json`](regions.json) (name, bounding box, center, zoom) and run `./setup.sh` again. The example regions are California and France, the two it was tested with. Map files are pulled from the latest daily [Protomaps](https://protomaps.com) build in pieces of up to 5×5°, so a dropped connection only costs one piece.

## Pages

| Page | What it's for |
|---|---|
| `/` panel | Connections, live numbers, gears, auto-shift, climbing, ERG, workouts, FTP test, personal bests, live graph, phone pairing |
| `/ride` | 3D ride view and handlebar remote (phone / tablet / computer) |
| `/plan` | Route planner: search, A→B, loops, "by distance", famous-ride ideas, GPX import |
| `/coach` | Morning diagnostic, today's verdict and plan, timed-workout builder |
| `/workouts` | Block-based workout builder |
| `/fitness` | Fitness, fatigue and form from power |
| `/milestones` | Streaks, totals, badges |
| `/posts` | Ride infographics, captions, the Claude pack, optional Strava |

## Coaching with Claude (optional)

Everything the pages can do is also available headless, so an AI coach can read your data and write your plan:

- **Command line:** `./hub today`, `./hub rides`, `./hub fitness`, `./hub checkins`, `./hub plan --verdict easy --note "…" --workout ID`, `./hub split --total 30 --intervals 3`. Run `./hub --help` for the rest.
- **MCP server:** [`mcp_server.py`](mcp_server.py) exposes 14 tools (today, check-ins, rides, a ride's full story, fitness, milestones, workouts, set today's plan…) to Claude Code or Claude Desktop:

  ```bash
  claude mcp add --scope user s-bike-hub -- "$PWD/.venv/bin/python" "$PWD/mcp_server.py"
  ```

  For Claude Desktop, add the same command under `mcpServers` in `~/Library/Application Support/Claude/claude_desktop_config.json`. The tools talk only to the hub on your Mac, and the bridge must be running.

## Your data stays on your Mac

Everything lives in the project folder and is git-ignored: rides (`rides/`), saved routes, your profile and FTP, personal bests, check-ins, the phone-pairing PIN and tokens, and optional Strava keys. Nothing is uploaded unless you press **Post to Strava**.

**The phone remote is plain HTTP on your home Wi-Fi.** It's protected by a PIN or one-time QR code, a long random token per paired device, and rate-limiting. It's meant for a home network, not the internet. Stopping the bridge is Mac-only.

## Other bikes

The hub talks standard **FTMS** (Fitness Machine Service) over Bluetooth, but the S29 has quirks it works around:
- **Resistance:** the S29 has 16 resistance levels that accept "target resistance" commands. It acknowledges "simulation" (hill) commands but ignores them.
- **Commands that reboot it:** "resistance 0" and an FTMS reset, so the bridge never forwards unchecked commands.

To try another bike:
1. Run `.venv/bin/python scan.py` with the bike awake, to see what it advertises.
2. Start the bridge with `--name <start of its Bluetooth name>`.
3. If resistance doesn't respond, the places to adapt are `set_level` and the command filter in `bridge.py`.

Reports and pull requests for other bikes are very welcome.

## Development

```bash
tests/run_all.sh        # 22 test files: auto-shift, ERG, FTP test, routes, pairing, coach, MCP, adherence…
```

- `bridge.py` is the Bluetooth bridge, gears, ERG and the ride loop.
- `panel.py` and `mapserver.py` serve the web pages and the JSON API.
- `web/` holds the pages.
- Routes and maps: `routes.py`, `planner.py` (BRouter), `pmtiles_reader.py`, `places.py`.
- Training: `coach.py`, `workouts.py`, `bests.py`, `fitness.py`, `milestones.py`, `adherence.py`.
- Posts: `story.py`, `card.py`, `posts.py`, and `strava.py` (optional).

## ⚠️ Safety

This software changes the resistance on real exercise equipment and relies on reverse-engineered, bike-specific behavior. Use it at your own risk, and keep a way to stop pedaling safely. It's not medical advice. Check with a doctor before starting a training program, and stop if something hurts.

## Credits

- **Map data:** © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL), via [Protomaps](https://protomaps.com).
- **Terrain:** [Mapzen terrain tiles](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) (AWS Open Data).
- **Software:** routing by [BRouter](https://github.com/abrensch/brouter); maps drawn with [MapLibre GL JS](https://maplibre.org); Bluetooth via [bleak](https://github.com/hbldh/bleak) and [bless](https://github.com/kevincar/bless); menu bar via [rumps](https://github.com/jaredks/rumps) and [PyObjC](https://pyobjc.readthedocs.io).

Built by JHarp199345 with [Claude](https://claude.com) as co-author.

## License

[MIT](LICENSE).
