# Bike setup: recognized bikes, and "get my bike working"

## What the athlete does

1. Open the hub's welcome page → **Your bike** → **Scan for my bike** (bike on, pedal to wake it, disconnected from phone and watch apps).
2. Click their bike in the list. The likeliest one is highlighted; nothing is chosen for them.
   - **✅ Recognized** (a saved or built-in profile, e.g. the Merach S29) or **✅ Standard smart bike** (speaks FTMS): **Use this bike**. Done, no AI involved.
   - **❔ Not recognized yet**: **This is my bike** → *May the hub ask your assistant to set this bike up?* → **Yes**.
3. On **Yes**, the hub listens to the bike for a few seconds and queues a request. The page says: **Open your AI assistant and type: get my bike working**.
4. The assistant (any MCP app with the hub's server installed) takes it from there. The page shows each step and when to pedal.

## What the assistant does

Its first tool, `get_bike_setup_request`, hands over the bike's Bluetooth name, services, readable values and captured data packets (no training history), plus the steps, safety rules and profile format. Then it:

1. Names the bike and asks the athlete to confirm it's theirs.
2. Has them pedal at 60 rpm, then 90 rpm (`capture_bike_data`): the byte that follows is cadence. Then the same cadence with the resistance knob turned up: the field that rises is power (speed doesn't).
3. Proposes a **profile** (`propose_bike_profile`): data, never code. The hub validates it and decodes every capture with it, warning on unbelievable numbers.
4. Asks "pedaling steadily and ready?", then runs the hub's **guided check** (`run_bike_check`, which requires `athlete_ready: true`).
5. Asks whether the pedals got harder in the middle (`record_bike_feel`), then activates it (`activate_bike_profile`), optionally with a pre-filled GitHub issue so the next owner needs no assistant.

If no resistance command can be confirmed, the profile can be **read-only** (`"resistance": {"none": true}`): power and cadence come in, and the athlete uses the bike's knob.

## Safety: enforced by the hub, not the assistant

- Every write during setup and riding passes `bikes.allowed_write`: FTMS resets, resistance 0, out-of-range levels, blocked commands and any bytes that aren't the profile's own commands are never sent.
- Inspection and captures only listen.
- The guided check starts from an easy level, steps one level at a time (at most one write per half second), holds, comes back down, and stops at the first sign of trouble (a disconnect means the bike rejected a command; nothing more is sent).
- A profile becomes the bike only after the check passed and, when resistance was tested, the athlete felt it.

## Files

| File | What |
|---|---|
| `bikes.py` | Profiles, validation, identification, safety rules, the request queue (no Bluetooth) |
| `bike_ble.py` | Scan, inspect and capture over Bluetooth (bleak); simulated bikes for tests (`S_BIKE_SIM=1`) |
| `bike_check.py` | The guided check |
| `bike_api.py` | `/api/bike/*` for the welcome page and the MCP tools |
| `bike_profiles/` | Built-in and shared profiles (Merach S29) |
| `bike.json`, `bike_setup.json`, `bike_profiles_local/` | This computer's bike, request and profiles (git-ignored) |

## How it's tested

- `tests/test_bike_setup.py` (Linux and macOS in GitHub Actions): matched bikes (S29 known, a standard FTMS bike), an unrecognized bike with its own protocol, a speaker and a heart-rate strap; consent; every MCP tool; wrong profiles caught (wrong power field, wrong cadence field, wrong resistance command, no pedaling); safety refusals; the bridge connecting with the result.
- The CI workflow also starts the real hub in no-bike mode with simulated bikes and checks the scan over HTTP.

### Live run with a real assistant (2026-10-03)

A real assistant with **only** the hub's MCP tools (no file or shell access, so it couldn't read the simulator's source) was given an unrecognized simulated bike and the single message `get my bike working`. It:

- named the bike and asked the athlete to confirm it,
- asked for 60 rpm and 90 rpm captures and found cadence (byte 2),
- held cadence and asked for the knob turned up, and found power (bytes 3–4) and resistance (byte 5), correctly telling power apart from speed (bytes 6–7),
- asked "ready?" before the check,
- guessed a resistance command that was close but wrong; the bike dropped after that **one** command and the hub sent nothing more,
- explained this, recommended read-only instead of blind guessing, activated on the athlete's OK, and offered the share link without posting anything.

The next scan listed the bike as **Recognized**.

An earlier run, before the knob guidance was added, mistook speed for power (both rise with cadence) and didn't ask "ready?" before the check. Both led to changes: the knob step in the instructions, and `athlete_ready` being required.
