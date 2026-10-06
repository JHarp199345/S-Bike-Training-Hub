# App 1.8.1 — music library and clearer workout records

## Available in this release

- One typed cycling builder, with power bands, cadence bands, time targets, live local previews, and reusable starter workouts.
- Private music library: songs, albums, artists, cover art, queue controls and available tempo/cadence suggestions. Music does not change workout targets.
- Recorded time distinguished from planned time. Imported daily activity totals stay visible when no matching prescription is saved, without adding duplicate training load.
- The shared Ride menu serves map, animal, pixel, haunted and personal-video views. Saved routes and ERG workouts are previewed separately from launching a ride.
- App icons for browser tabs and home screens.
- Clear in-progress labels and fixes for music setup refresh, duplicated upcoming-test labels and the idle video clock.

## In progress

- Apple Music publisher configuration and live-account verification.
- Plex real-account audio/video verification. Browser-playable personal MP4/WebM files only; no transcoding, subtitles or watch-progress integration.
- iBroadcast and OpenSubsonic connection setup.
- Native saved-folder chooser and automatic audio decoding for tempo on Linux/Windows. Browser-local audio files are available; existing BPM tags can be used.
- Further calibration and adaptive-programming work listed under What's new. Training-model outputs remain provisional estimates.

## Installation and updates

Download this release's source archive, extract it, and follow the platform setup steps in the README. Update your existing checkout using Git if that is how you installed it. Preserve your local athlete data and settings; this release contains no athlete records, personal workouts or music.

The assistant protocol is unchanged: use **MCP 1.8.0**, included as the existing verified bundle for convenience. Existing MCP 1.8.0 users do not need to reinstall it for these app changes. The desktop bundle currently declares macOS compatibility; app source and its platform scripts are separate from that extension.

What's new and optional update notifications identify this app update. They never install it automatically.

## Verification scope

The release runs the Python suites and browser calculation/interaction checks on macOS, Ubuntu and Windows in GitHub Actions. Tests include no-bike HTTP startup and simulated trainer behavior. Automated software tests do not certify physical Bluetooth/watch compatibility, real media accounts, GPU rendering on every device or physiological accuracy.
