# S-Bike Training Hub

**Turn a budget smart bike into a full training setup: offline 3D routes, virtual hills and gears, auto-shifting, ERG workouts, a phone handlebar remote, and a training-load model that covers every sport you do, not just the bike. It runs entirely on your Mac, with no subscription and no cloud.**

It was built for, and has only been tested on, the **Merach S29**. Other smart bikes that speak Bluetooth FTMS may work, but we couldn't test them (see [Other bikes](#other-bikes)).

**Merach S29 owner? The problems this was built to fix:**
- **Only one thing can connect to the bike at a time**, so your watch can't record power and cadence while Zwift or Kinomap is connected. The hub holds the one connection and shares it with both.
- **Hills didn't change the resistance** in Zwift or Kinomap on our S29: it ignored the apps' hill commands. The hub turns the grade into resistance itself, eased in smoothly.
- **No gears, and no virtual shifting.** The hub adds virtual gears and auto-shifting that keeps your cadence in a band, plus big shift buttons on your phone.
- **ERG that grinds you to a stop when you tire.** The hub's ERG works in zones around the target, backs off when your cadence falls, and pauses and resumes the workout.
- **No subscription needed:** routes, workouts and training load all run on your Mac.

Newer S29 units, and the S29R2 (2026), may handle hills in Zwift and Kinomap on their own; we haven't tested them.

<p align="center">
  <img src="docs/ride-view.png" width="300" alt="The 3D ride view on Alpe d'Huez: speed, watts, cadence, grade, gear, a ghost race and the climb profile, with big shift buttons">
  &nbsp;
  <img src="docs/ride-post.png" width="380" alt="An automatic ride-post infographic with records, milestones, a power chart and time in zones">
</p>

## What it does

The S29 only accepts **one** Bluetooth connection, and it ignores the "hill" commands that training apps send. The hub sits in the middle: it holds the single connection to the bike, and then:

- **Shares the bike.** It re-advertises the bike as a new device ("SBike Hub"), so a watch (power + cadence) and a training app can connect at the same time.
- **Makes hills real.** Grades from a route or a training app become resistance, eased in smoothly, with **virtual gears** on top.
- **Auto-shifts.** It keeps your cadence in a band (65–80 rpm by default), shifting sooner the harder you spin. With a **daily focus** it also steers your watts into a range: easy but still productive. A **climbing mode** handles low-cadence standing efforts.
- **Computes virtual speed** from watts, weight and grade, so climbs feel like climbs.
- **Runs ERG workouts.** It holds a target wattage whatever your cadence. In a workout it works in zones around each block's target instead of chasing every watt: green (90–120%) never shifts, yellow (80–90% / 120–140%) is still on the road and shifts after 2 minutes, red after 30 seconds, black after 8. Before it shifts, it checks where the next gear would land, and it won't shift you off the road. FTP tests and Kinomap keep tight control.
- **Pauses and resumes.** The workout clock only runs while you pedal with the bike connected: stop and it pauses by itself, or tap ⏸. If a workout stops before it's done (you tapped End, the page reloaded, the bridge restarted), the Coach page and the game view offer **Resume** for the rest of the day, at the same block and second. The pieces of a day's ride count as one session.

<p align="center">
  <img src="docs/resume-coach.jpg" width="280" alt="The Coach page with a purple Resume bar at the top: Resume, 5:24 into the planned workout, block 2 of 4, 25 minutes left, the clock waits for your pedals (sample data)">
  <img src="docs/resume-game.jpg" width="200" alt="The game view's start card offering Resume your workout, 5:24 in, 25 minutes left, above a smaller Start a course button (sample data)">
</p>


On top of that:

| | |
|---|---|
| 🗺 **Offline routes in 3D** | Plan A→B rides, loops, or "N km in any direction" rides on real roads, with a local BRouter route planner. Search towns and mountains offline, or tap famous rides (Alpe d'Huez, Ventoux, Tourmalet, PCH…). Then ride them in a tilted 3D follow view with real terrain and buildings. You can import GPX from Strava, Komoot and others. |
| 📱 **Phone / tablet handlebar remote** | The ride view works on any phone or tablet on your Wi-Fi (on a phone, the numbers and the route take turns at the top, Kinomap-style, so the map gets the screen): giant shift buttons with vibration, a drawer for auto-shift, climbing mode, ERG and workouts. Pair by scanning a QR code on the Mac (a one-time code) or typing a PIN. |
| 👻 **Ghost racing** | Race your last ride on the same route: "14 s ahead". |
| 🎚 **Daily focus** | Each day has a cadence range and a watt range: cadence habit (65–80 rpm, zone 2), grit (big gear, low cadence), leg speed, recovery, or your own. Auto-shift steers toward both, and a quiet monitor on the ride view shows time in range, with a hint only after you've drifted for a while. |
| 📍 **Area routes** | Circle where you'd like to ride and say how long. The planner finds loops inside the circle and ranks them for today's focus: time at the focus's watts (climbs slow you), how much of it auto-shift can hold in range, and whether the terrain suits the day. |
| ⛰ **Climb goals & efforts** | Put training on a route's climbs: "climb 2 in 10:00" becomes a watt target re-worked every second from what's left, and "3 × 15 s at 200 W" shifts you straight into a big gear. Every climb you ride is recorded (time, watts, cadence, VAM), and the planner knows the fastest time your **W′** could cover. |
| 🎮 **Game view** | A ride with no map route becomes a side-scroller whose hills are the workout. Plan a ride (a course sized to the planned minutes) or hit **Ride now** on a workout (terrain drawn from its blocks). Stay inside your cadence and watt ranges to ride the **lit road** and evolve through your chosen animals: bike → unicorn → wolf → eagle → dragon, or any order you pick from 17. Spin and push **gates** ask for the top of your range for 10 seconds. **Modern** (soft layered silhouettes, dawn to dusk) or **8-bit**. Saved map routes open here too, with their real hills, and 🎮 / 🗺 switch views mid-ride. See [The game view](#the-game-view). |
| 🧭 **Coach** | Three tabs: **Today** (the verdict and your morning check-in, right on the card), **Plan** and **Progress**. This week at a glance (a marker per day, including swims your watch calendar can't hold), a one-tap effort rating, morning readiness from your watch (HRV, resting heart rate, sleep), **skill ladders** that step up and down with the evidence, **test weeks**, and a calibration card for every capacity. A 6-minute **morning diagnostic** (fixed watts, heart rate read off your watch) gives a go / easy / rest verdict against your own normal. The **timed-workout builder** lets you pick a length, drag bars, and see the parts rebalance in proportion. A short **journal** goes with each check-in. It's never scored, but it raises a **flag** when your words and your sliders disagree (see [The journal flags](#the-journal-flags)). |
| 🫀🦶🦵 **Training load for every sport** | Runs, walks, swims, gym and rides from your watch, scored on three body systems: **heart & lungs**, **feet & bones**, **leg muscles**. You get separate **bike** and **running** verdicts, and the running load is tracked as accumulated "blocks" that recover on a realistic, slow timeline. Tap any system for its graph, readings, and the sessions behind it. See [Training load: how it works](#training-load-how-it-works). |
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
  <img src="docs/coach.png" width="480" alt="The Coach page, Today tab (sample data): the verdict, this morning's check-in with the hop test per leg and a journal entry, a journal flag asking to be confirmed, and the cardio and mechanical load cards">
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
   - set yourself up in `profile.json` in the project folder: `{"weight_kg": 80, "hr_rest": 60, "hr_max": 185}`. Weight drives virtual speed and running impact; the heart rates drive the heart-rate load. Your FTP gets saved in the same file.
   - in the planner, move the map to where you ride and press **📍 Home view**.
5. **Put your phone on the handlebars.** Scan the QR code in the panel's *Phone remote* box (same Wi-Fi), and it opens the ride view, paired.

### Choosing map regions

Edit [`regions.json`](regions.json) (name, bounding box, center, zoom) and run `./setup.sh` again. The example regions are California and France, the two it was tested with. Map files are pulled from the latest daily [Protomaps](https://protomaps.com) build in pieces of up to 5×5°, so a dropped connection only costs one piece.

## Pages

| Page | What it's for |
|---|---|
| `/` panel | Connections, live numbers, gears, auto-shift, climbing, ERG, workouts, FTP test, personal bests, live graph, phone pairing |
| `/ride` | 3D ride view and handlebar remote (phone / tablet / computer) |
| `/plan` | Route planner: search, A→B, loops, "by distance", **area** (routes for today's focus), a route's climbs with time goals and efforts, famous-ride ideas, GPX import |
| `/coach` | This week, today's bike and running verdicts, the day's focus, morning readiness, effort rating, the body systems (tap for detail), coming up, calibration, progressions, the morning diagnostic, the timed-workout builder |
| `/course` | The game view: today's course, a running workout, or the route you're riding |
| `/workouts` | Block-based workout builder |
| `/fitness` | Fitness, fatigue and form from power; body systems across every sport; the aerobic engine (watts per beat, decoupling); how your sports carry over |
| `/milestones` | Streaks, totals, badges |
| `/posts` | Ride infographics, captions, the Claude pack, optional Strava |

## The game view

<p align="center">
  <img src="docs/game-modern.jpg" width="200" alt="Game view, Modern look: a white unicorn galloping along the glowing lit road at dusk, with the Focus overlay showing cadence 65 and watts 112 inside their ranges">
  <img src="docs/game-workout.jpg" width="200" alt="Game view during a builder workout: a dragon breathing fire above the road, with the Workout overlay showing the target watts, time left and every block">
  <img src="docs/game-8bit.jpg" width="200" alt="Game view, 8-bit look: a pixel-art unicorn on the lit road, with the Form overlay showing progress to the next form and the streak">
  <img src="docs/game-forms.jpg" width="200" alt="The Forms editor: the chosen forms in order (unicorn, wolf, eagle, dragon) and the other animals to add">
</p>

- **Where the terrain comes from:**
  - **A planned ride with no route:** warm-up, steady climbs with short descents between them, cool-down. It's sized so it takes the planned minutes at your focus's middle watts, and the bridge rides it like any route, so auto-shift and the focus work as usual.
  - **A workout from the builder:** it runs in ERG, and the terrain comes from its blocks (harder blocks are steeper). The picture follows the workout's clock, so the next interval shows as a hill ahead.
  - **A saved map route:** its real elevation profile.
- **The lit road:** inside both your cadence and watt ranges (in a workout, watts near the block's target). Time on it evolves you, **5 minutes per form**; a minute off it drops you one form, not all the way.
- **The animals:** 17 of them, filmed from CC0 3D models by [Quaternius](https://quaternius.com) into sprite strips, in colour. The farm animals walk below about 16 km/h and gallop above about 19, so pace shows as a change of gait. Pick your forms and their order from **☰ → Forms…**; the choice is kept on the bridge.
- **Overlays:** the ride's numbers come one card at a time - Ride, Focus, Graph (the last 10 minutes), Route, Workout, Form - cycling every 8 seconds. Tap or swipe to move on, 🔒 to hold one. Something happening jumps to its card for a few seconds. Watts and cadence stay up top. The map view uses the same overlays on phones.
- **Yellow is on the road too:** in a workout, watts within 80–140% of the block's target count toward your forms and gates. Red and black don't.
- **No map where there's no road:** a watts-and-cadence workout, or a made-up course, only rides in the game view.

## Coaching with Claude (optional)

Everything the pages can do is also available headless, so an AI coach can read your data and write your plan:

- **Command line:** `./hub today`, `./hub rides`, `./hub fitness`, `./hub load`, `./hub checkins`, `./hub checkin --feet 4 --legs 5`, `./hub steps 2026-09-27=6200`, `./hub import FILE.fit`, `./hub plan --verdict easy --note "…" --workout ID`, `./hub split --total 30 --intervals 3`. Run `./hub --help` for the rest.
- **MCP server:** [`mcp_server.py`](mcp_server.py) exposes 45 tools (today, check-ins, rides, a ride's full story, fitness, body-system load, importing watch files, daily steps, morning readiness, effort ratings, the day's focus and plan, area routes, climb goals, skill ladders, calibration and tests, test weeks, the aerobic engine, sport carry-over, milestones, workouts…) to Claude Code or Claude Desktop:

  ```bash
  claude mcp add --scope user s-bike-hub -- "$PWD/.venv/bin/python" "$PWD/mcp_server.py"
  ```

  For Claude Desktop, add the same command under `mcpServers` in `~/Library/Application Support/Claude/claude_desktop_config.json`. The tools talk only to the hub on your Mac, and the bridge must be running.

We deliberately didn't build a multi-week planner. The load model says how much running your body can take and when; an AI coach with these tools can turn that into a plan that fits your week, your goals and how you feel, and change it tomorrow. If your AI also has a connector for your watch (COROS, for example), it can pull in your activities and daily steps with `import_activities` and `record_steps`.

## Training load: how it works

Most apps give you one "training load" number. It adds up a hard ride, a run and a gym session as if they cost the same thing, and it tells you you're fresh when your legs and feet say otherwise. That's the gap this model was built to close.

> ⚠️ This is an **experimental planning model**, not a measurement of your body. It has been tuned against one rider's real training and how it felt. The numbers are starting points that adapt to you (see below). It doesn't diagnose anything: if something hurts, stop and see someone.

### Three body systems, one verdict per sport

Different parts of you adapt at very different speeds. Your heart and lungs catch up in days, but tendons and bone take months. So every activity from your watch (runs, walks, swims, gym, rides) and every ride on the bridge is scored on three systems:

| System | What loads it | How it's scored |
|---|---|---|
| ❤️ **Heart & lungs** | everything | Rides with power: training stress from watts (TSS: time × intensity², 100 = an hour at FTP). Everything else: heart-rate load (Banister TRIMP), converted to the same points using **your own rides that have both watts and heart rate**. |
| 🦶 **Feet & bones** | running, walking | Every step's force, raised to the **4th power**. See below. |
| 🦵 **Leg muscles** | bike, running, gym | Bike: pedal torque each second, squared, so grinding at low cadence counts extra. Running: body weight × distance × speed. Gym: effort (RPE) × minutes. Swimming: a trickle. |

Each system gets a **fitness** (long average: what it's used to) and a **fatigue** (last week), and their ratio:
- under 0.8: room to build
- 0.8–1.3: the sweet spot
- 1.3–1.5: caution
- over 1.5: rest. This is the zone where injuries cluster in the sports-science literature, using the acute:chronic workload ratio with Williams' exponentially weighted averages.

**Readiness is weakest-link:**
- The **bike** verdict comes from heart & lungs and leg muscles.
- The **running** verdict comes from feet & bones and leg muscles.
- The bike doesn't load your feet, so sore feet bench your running, not your riding.
- Your morning check-in (feet, legs, breathing, 1–10) can always make it more careful: 6+ means easy, 8+ means rest.

#### The journal flags
The journal is your own words, and it never moves a number by itself: letting words score invites drifting into a longer (or shorter) recovery without meaning to. Instead it **flags**:
- **Words vs sliders.** "Sharp pain in my shin" with feet & bones at 3/10, "pulled my hamstring" with legs at 2, or "fever" with breathing at 3. The other way too: "feel great, no pain" with feet at 7.
- **Something serious**, whatever the sliders say: swelling, a limp, can't bear weight, pain at night, chest pain.
- Negations don't count ("no sharp pain", "not swollen").

Each flag waits for you: **It's real - count it** or **It's fine**. Only a confirmed flag counts, the way moving its slider would: bone or muscle read as 6/10 that day (then judged by the phase rules), illness makes heart & lungs easy. An AI coach can settle a flag (`settle_journal_flag`) only on your say-so.

### Feet & bones: steps, force, and blocks

Running is the scarcest resource, and it's the most closely managed.

**1. Every step is a force.**
- Steps come from your watch's cadence.
- Each step's peak force is estimated from your weight and speed: about 1.2 × body weight walking, 2 + 0.2 × speed (m/s) × body weight jogging, more downhill.
- Damage per step rises with the **4th power** of that force. This is the exponent in Carter's "daily stress stimulus" for bone: tissue fatigue rises steeply with load per cycle.
- So a step 20% harder does about twice the damage, and a walking step does roughly a tenth of a jogging step's.
- The detail view shows each run's steps, average force in pounds, and its damage as **"steps at 1,000 lb"**.

**2. Runs add up in blocks.**
- **One block** is your own unit: the median of your first three runs, with an estimate for an unconditioned body at your weight as the floor.
- A run landing on load that's still there costs extra, up to ×4 on top of a heavy load. So the same run two days in a row costs far more the second time.
- Days already served count. A new run adds 5 days per block it added to whatever plateau is still owed: run (5 days), a day passes (4 left), run again as 2 blocks (+10) = 14 days.

**3. Blocks recover slowly, in three phases.** The timing scales with the load, with no cap:
- a **plateau** of about **5 days per block**, when nothing seems to heal
- a **decline** over about **3 days per block**, down to a fifth
- a **remodeling tail** of about four months (a bone remodeling cycle)

So a load of 2 blocks plateaus about 10 days and declines over about 6. A load of 13 blocks plateaus about 65 days (less the days served between the runs that built it) and declines over about 39, then the tail. Recovery time per block is the same at every level of fitness; conditioning changes how much running a block holds, not how long it takes to clear.

**4. Running is cleared by the blocks.**
- Over **1.5 blocks** means rest, and over 1.0 means easy.
- In the tail, running is blocked only above 1.1 × the limit.
- A tail day when your feet and legs both check in at 2/10 or better allows a short, easy run.
- **The hop test.** Coming back from a block, running also needs a recent (last 3 days) single-leg hop test: **10 pain-free hops** on the worse leg. Log each leg in the morning check-in; the worse one is the number.
- A separate **five-day "recent run response"** catches the day-after hit of a single run.

**5. Walking counts too, but lightly.**
- Your watch's daily steps, minus the steps in your runs, are your walking.
- **Free steps.** No step is free, but your feet repair a daily budget, and walking inside it doesn't pile up. The budget comes from your conditioning, whichever is bigger:
  - **running:** one day's repair (1/8 of your block, to start) in your own walking steps. A bigger block from benchmark runs means more free steps.
  - **walking:** what you've walked and woken up fine from (at least three good mornings in 60 days), scaled to a fresh foot.
  - Biking and swimming earn nothing: they don't load feet and bones.
- **Your mornings correct it.** A rough morning after a day over the line (feet or legs 6/10+, or hops down 2+) lowers the running-side estimate; a good one raises it, more slowly.
- The free steps **shrink as your load rises**: about 60% of fresh at 13 blocks, never below a quarter.
- Only the steps over the line count, and only they carry the "load already there" multiplier, scaled down to match how light a walking step is.
- Walking extends the plateau (5 days per block) instead of restarting it. A few quiet days let it drain; weeks of 10,000+ steps with no rest don't.

The Coach page shows all of it:
- the bike and running verdicts
- a tappable card for each system, with a 28-day graph, the readings, the sessions behind the score, your matching check-ins, and "how this score is computed"
- the blocks graph with its no-new-running projection
- the walking table

### How it was conceived

It was built in about two days of real use, one iteration at a time, each driven by a mismatch between the numbers and the rider's body:

1. **Load ratio across sports.** A standard acute:chronic ratio per system. The first version flagged a perfectly steady routine as dangerous, because its averages were too slow. It switched to Williams' exponentially weighted version, plus a rule that keeps a system on "easy" for a week after a spike.
2. **Heart rate married to watts.** Runs and swims have no power, so heart-rate load is calibrated against the rider's own rides that have both.
3. **Capacity from how the body responded.** The engine handled a big week like easy work while the feet were clearly overdone. So each system's "usual week" can be tuned to what the body actually showed.
4. **Step-based, superlinear impact.** The rider's own arithmetic set this off: thousands of steps at several times body weight is a lot of force for an unconditioned body. Distance became steps × force⁴.
5. **Tissue clocks.** A damage-and-repair model with separate clocks for soft tissue, tendon and bone. It's kept as the "exploratory tissue detail" on the fitness page.
6. **Blocks.** The rider worked out the plateau / decline / tail shape with ChatGPT, matching how the recovery actually felt, and it matched: rest for running, easy for the legs, go for the engine.
7. **Walking**, then the uncapped timeline and the tail rule, in the same way.

### How it adapts to you

Nothing here is fixed to the person it was first tuned on. With real use it learns:

| What adapts | From |
|---|---|
| **Heart-rate → points conversion** | The median ratio of watts-based load to heart-rate load on your own rides with both. |
| **Your jogging step** | Runs without cadence (older .tcx exports) are scored from the per-step force and cadence of your runs that have it. |
| **The size of a block** | Your first three runs, then **benchmark runs**: 2 miles on the same flat loop at a fixed easy pace. Each is graded once the two mornings after are in, on how it felt (1-10), heart rate against the prediction from your last benchmarks, your check-ins leading up to it, and those mornings. Growth follows diminishing returns (about 10% at your starting block, a sliver near 5×), and results overrule the curve: beat the prediction and it grows more and the curve shifts up; fall short and it grows little. Anything hurt, or a 6/10+ morning after: no growth, repeat it. Shown recovery also earns up to +30%: at least four runs over four or more weeks, each followed by three run-free days and reassuring check-ins. |
| **How long a plateau lasts** | Your check-ins after each run, judged against where you should be. Beat-up mornings (feet or legs 6/10+, or 3 or fewer pain-free hops) in the first half of the plateau are expected, so they're neutral unless getting worse morning to morning; past halfway they add half a day each. Good reports shorten it by half a day each, after more than two. |
| **Each system's usual week** | Tuned from how your body responded: `./hub capacity impact 150 --note "feet sore at this"`, the `set_capacity` MCP tool, or your AI coach. |
| **Fitness** | The long averages rise as you train steadily. |
| **Your normal morning** | The diagnostic verdict compares you with the median of your recent tests. |

Settings in `profile.json`:
- `habitual_steps`: your ordinary day, default 6000
- `gym_rpe`: effort for gym sessions with none logged, default 5
- `training_phase`: `run_durability`, `aerobic_base` or `bike_performance`, which weights the headline balance grade
- `load_calibration`: tuned usual weeks

### Getting your watch data in

- **Activities:** drop `.fit` or `.tcx` files into `activities/`, or run `./hub import FILE_OR_URL`. Duplicates, like the same ride from the watch and the bridge, are counted once; the copy with power wins.
- **Daily steps:** `./hub steps 2026-09-27=6200`, or the `record_steps` MCP tool.
- **Check-ins:** the Coach page, or `./hub checkin --feet 4 --legs 5 --breathing 3`.

### Readiness from the watch overnight

If an AI coach has your watch connected (COROS, for example), it records each morning with `record_morning`:
- **HRV:** below the watch's own normal range makes heart and lungs **easy**. Two mornings running makes it **rest**.
- **Resting heart rate:** 5+ beats over its two-week median means easy, 8+ means rest.
- **Sleep:** under 5 hours means easy.

A rest morning benches running too.

### Progressions and regressions

Each skill is a ladder of concrete steps, after Michael Boyle's approach:

| Skill | Ladder |
|---|---|
| Cadence habit | 65–80 → 70–85 → … → 85–100 rpm |
| Leg speed | faster ranges |
| Grit | longer, harder big-gear sets |
| Climb pace | goals from 110% down to 94% of your best time |
| Running return | walking only → 1:2 jog/walk → … → 30 minutes |

- **Up:** two good sessions on a step earn the next one. Evidence only counts from when you reached the step.
- **Down:** two poor sessions, or a very hard effort rating on grit, drop you one.
- **For the day:** when you're not recovered, you ride one step down without losing your place.
- **Running** drops to walking while it's on rest.

The day's focus and the planner's climb goals use your current steps.

### Calibration and test weeks

Every capacity (FTP, heart rate at 90 W, a big-gear 3-minute test, critical swim speed, the running block, CP and W′) is an estimate combining three things: the latest test, training evidence since then, and anything you set by hand. Each one shows a **confidence** that fades until the next test comes due.

**Tests are plan items, not buttons.** They run from the Coach page's "Ride it" row or the Tests group in the ride menu.

**A test week doubles as a recovery week,** every 6 weeks:

| Day | Session |
|---|---|
| Mon–Wed | easy, reduced sessions |
| Thu | swim CSS test |
| Fri | the 6-minute morning diagnostic, then rest |
| Sat | **test day:** FTP ramp test, or the big-gear test (never two leg tests on one day) |
| Sun | off |

You test at your peak, then start the next block fresh.

**What the results feed:**
- **Swims** are scored against your CSS (hours × (CSS ÷ pace)³ × 100).
- **The running block** grows by up to 10% after a benchmark run followed by two good mornings.

### Power: CP, W′ and the aerobic engine

**Critical power and W′:**
- **The fit:** CP and W′ come from your best efforts over 3–20 minutes (the 2-parameter model).
- **When it's trusted:** easy rides produce a tidy curve that sits well below your limits, so the fit is only used once CP reaches 85% of FTP. Until then the hub shows it as a floor and uses FTP with a typical W′.
- **Live W′ balance** (the differential model) appears on the ride view once you dip into it, and counts "matches".
- **Doability checks:** climb goals and efforts are checked against W′ before you ride them.

**The aerobic engine,** from your watch's ride files (the watch records power and heart rate together):
- **Watts per beat** (normalized power ÷ heart rate) rises as you get fitter.
- **Heart rate at a fixed 100–120 W** falls.
- **Aerobic decoupling:** watts per beat in the first half vs. the second. Under 5% means the ride stayed aerobic. It's only judged on steady rides of 40+ minutes.

### What the watch saw

<p align="center">
  <img src="docs/insights.jpg" width="320" alt="Coach, Progress tab, What the watch saw (sample data): flags that ask questions about a sudden stroke change in a swim, run form drift, and a ride with four pauses; trends for how long the stroke holds and ride recovery; a swim opened to its sets, with SWOLF, strokes and pace per set and the sudden step at length 8">
</p>

Beyond the loads, the hub reads the rest of each watch file and cross-references it (**Coach → Progress → What the watch saw**, and `get_insights` for Claude). It flags with the numbers behind it and a question. It never scores, and it changes no load number.
- **Swim, length by length:** SWOLF (seconds + strokes), stroke rate and pace, set by set. Where the stroke changes, by how much and how fast: **held**, **gradual** (a slow fade: ordinary fatigue) or **sudden** (a step between neighbouring lengths; even a small one is the more telling strain signal), and what moved (more strokes, or slower). A set's first length, off the wall on fresh arms, is left out. Across swims it shows how far in the stroke usually breaks down, which is the session length it can hold. Heart-rate drop in the rests is shown, but a wrist in water reads roughly.
- **Run:** laps and 5-minute splits of power, cadence, heart rate, pace, vertical oscillation and ratio, step length, and ground contact per lap. Form drift in the last third is judged only when the pace matched.
- **Ride:** work in kJ against the next morning's legs; heart rate in the opening minutes against your usual at those watts; how far heart rate falls in the minute after a hard effort; whether cadence and heart rate show the running load your legs carried in; heart rate on each climb against the last time up it.
- **Pauses:** stops mid-workout in every sport, counted and timed. A lot of them asks what was going on.
- **Attempts don't count:** a session under 10 minutes, or under half its planned time, isn't marked done or offered for rating.

The thresholds (a 2-point SWOLF step, a 5% fade) are starting points to check against how the sessions felt.

### Swim recovery

A separate swim recovery estimate reads active pool lengths from the watch: `strokes × stroke factor × (length speed / 0.9 m/s)²`, adjusted for paddles, pull buoy and perceived effort. The stroke factors and gear multipliers are provisional tuning choices, not measured tendon forces. One provisional block starts at three times the median dose of the first three swims, then is **fitted continuously** to next-morning shoulder reports: a Bayesian fit over candidate block sizes, with the first-swims value as a log-normal prior, with an 80% interval that narrows as reports come in. The 1.5-block line is a planning convention, not an injury threshold. The Coach's body map (anatomy from [body-highlighter](https://www.npmjs.com/package/body-highlighter), MIT) shows where each sport's load lands; the colours are relative participation, not measured forces.

### Lifting and functional strength

A gym session is a list of exercises: barbell lifts, medicine-ball throws, cable and band moves, holds and hangs. List them yourself on the Plan tab (name, sets × reps or time, weight, tempo), or ask your AI to build the session. The AI scores it: the kind of exercise, whether it's **restorative** or **build** work, and how each movement's strain is shared across the body.
- **The check-off** after the workout runs down the list. More weight than planned counts as more load. Less weight asks why: *too heavy* keeps the planned load and lowers the strength estimate; *chose to* counts what you lifted.
- **Each muscle group gets a recovery block**, tuned by a follow-up two to four days later. Leg work shares the leg budget with running and riding.
- **The Rules tab** holds your line items: "No barbell squats" is enforced, favourites come up often, anything else guides the AI.
- **The steer** suggests how much of a session should be restorative: 5-10% when you're fresh, about 80% when any system is at its limit. Your after-session and follow-up reports move the curve, and your own call always wins.

- **Calibration on a schedule:** a follow-up three days after every lift session, and a **Sunday check-in** (open through Tuesday) that asks only about what your week held: legs if you rode, feet and the hop test if you ran, shoulders if you swam, each muscle group you lifted, and the week overall. The running, swim and lifting models learn from it and trust it most.
- **Lifting carries over:** a muscle group's lifting load counts toward the mechanical load, and toward each sport's verdict by how much that muscle works in the sport. A heavy shoulder day makes the swim verdict easy; kneeling core work barely touches running.

How to use it with an AI coach, and the thinking behind it: **[the wiki](https://github.com/JHarp199345/S-Bike-Training-Hub/wiki/Training-with-your-AI)**.

### The dashboard

<p align="center"><img src="docs/dashboard.jpg" width="320" alt="The dashboard (sample data): today's verdicts for bike, running, swimming and lifting, then every piece of the mechanical load as a ring against its limit, and the cardio fitness, fatigue and form chart"></p>

**/dashboard** shows everything the hub computes in one place, each chart with a plain "what it means": today's verdict per sport; every piece of the mechanical load as a ring against its limit; cardio fitness, fatigue and form, and where the week's load came from; where the load lands on the body; lifting blocks, the steer's suggestions against what you did, and strength estimates; what the watch saw; and what every model has learned from your tests and reports. Today, Plan and Progress stay simple; the dashboard is where the detail lives.

### How the sports carry over

A carry-over table estimates how much training one sport builds another, compared with training that sport itself, plus how much each sport tires your legs compared with running.
- **Starting values** come from the research: cycling carries over to running (Millet et al. 2002); little carries into swimming; running carries to cycling better than the reverse (Tanaka 1994); and replacing some running with cycling at about 2:1 kept runners' fitness in a 2026 meta-analysis. **Only running builds feet and bones:** cyclists and swimmers carry little bone-loading benefit.
- **It learns your numbers** from every efficiency measurement and next-morning check-in. It uses Bayesian linear regression, which reaches the same answer a Kalman filter would one measurement at a time (after Kolossa 2017 and Swartz et al.).
- **Each value** shows an 80% range and whether it's still the research's number, learning, or learned.
- **Fitness carry-over is slow to pin down.** Weeks where the mix changes, plus test weeks, are what sharpen it.

## Your data stays on your Mac

Everything lives in the project folder and is git-ignored: rides (`rides/`), watch activities and daily steps (`activities/`), saved routes, your profile, FTP and load tuning, personal bests, check-ins, the phone-pairing PIN and tokens, and optional Strava keys. Nothing is uploaded unless you press **Post to Strava**.

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
tests/run_all.sh        # 37 test files: auto-shift, ERG, FTP test, routes, pairing, coach, MCP, adherence, training load, focus, sessions, calibration, CP/W′, carry-over…
```

- `bridge.py` is the Bluetooth bridge, gears, ERG and the ride loop.
- `panel.py` and `mapserver.py` serve the web pages and the JSON API.
- `web/` holds the pages.
- Routes and maps: `routes.py`, `planner.py` (BRouter), `pmtiles_reader.py`, `places.py`.
- Training: `coach.py`, `workouts.py`, `bests.py`, `fitness.py`, `milestones.py`, `adherence.py`.
- Training load: `fit.py` (a standard-library FIT reader), `loads.py` (every sport scored on three body systems, readiness), `damage.py` (the running blocks, walking, and the exploratory tissue model), `morning.py` (readiness from the watch overnight).
- Coaching: `focus.py` (the day's ranges), `session.py` (climb goals, efforts, climb records), `areaplan.py` (area routes), `skills.py` (progressions and regressions), `calibration.py` (capacities, tests, test weeks), `cp.py` (CP, W′, W′ balance), `aerobic.py` (watts per beat, decoupling), `transfer.py` (cross-sport carry-over, Bayesian).
- Posts: `story.py`, `card.py`, `posts.py`, and `strava.py` (optional).

## ⚠️ Safety

This software changes the resistance on real exercise equipment and relies on reverse-engineered, bike-specific behavior. Use it at your own risk, and keep a way to stop pedaling safely. It's not medical advice. Check with a doctor before starting a training program, and stop if something hurts.

## Credits

- **Map data:** © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors (ODbL), via [Protomaps](https://protomaps.com).
- **Terrain:** [Mapzen terrain tiles](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) (AWS Open Data).
- **Body map:** [body-highlighter](https://www.npmjs.com/package/body-highlighter) (MIT) - see [web/vendor/body-highlighter.LICENSE](web/vendor/body-highlighter.LICENSE).
- **Game art:** animals rendered from 3D models by [Quaternius](https://quaternius.com) (CC0) - see [web/sprites/CREDITS.md](web/sprites/CREDITS.md).
- **Software:** routing by [BRouter](https://github.com/abrensch/brouter); maps drawn with [MapLibre GL JS](https://maplibre.org); Bluetooth via [bleak](https://github.com/hbldh/bleak) and [bless](https://github.com/kevincar/bless); menu bar via [rumps](https://github.com/jaredks/rumps) and [PyObjC](https://pyobjc.readthedocs.io).

- **Science:** the models build on published work - Banister's fitness-fatigue model, Coggan's TSS/NP, Carter's daily stress stimulus, Williams' EWMA workload ratio, Skiba's W′ balance, Foster's session RPE, Millet et al. (2002) and Tanaka (1994) on cross-training, Boyle's progressions and regressions, and Kalman/Bayesian impulse-response fitting (Kolossa 2017; Swartz et al.). Formulas were cross-checked against [GoldenCheetah](https://github.com/GoldenCheetah/GoldenCheetah)'s open-source metrics; no code was copied.

Built by JHarp199345 with [Claude](https://claude.com) as co-author. The running-load block model was worked out by JHarp199345 with ChatGPT, then built into the hub with Claude.

## License

[MIT](LICENSE).
