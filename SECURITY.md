# Security policy

S-Bike Training Hub runs on your own computer and holds personal training and health records. It can talk to your
bike over Bluetooth, and, when you turn features on, use a device's camera or motion sensors and connect to outside
services. That access should be easy to check and hard to misuse, so this page says what the hub does with it and how
to report a problem.

## Reporting a vulnerability

Please report security problems **privately**, not in a public issue:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability** and describe what you found, how to reproduce it, and what it could affect.

Reports are read and handled as quickly as possible. This is a small, unfunded project: there is no bug bounty, and
fixes ship in the next release. Please give a reasonable chance to fix the problem before you share details publicly.

## Supported versions

Only the latest release is supported (the app and the assistant connection, MCP, each have their own version number;
see the [changelog](CHANGELOG.md)). Update before reporting, if you can.

## What the hub does with its access

- **Your records stay on your computer.** There is no S-Bike server and no telemetry. The hub makes an outside
  connection only for a feature you use, as listed under [Privacy](README.md#privacy) (for example the optional
  weather lookup, or posting a ride to Strava, which shows you the caption first).
- **Other devices must pair.** The hub listens on your home network so a phone or tablet can be a remote or a ride
  screen. A device other than the computer running the hub must pair first (a one-time code or PIN); only the computer
  itself can stop the hub or change accounts.
- **The secure port** (one above the usual port) exists because browsers allow games, the camera and motion sensors
  only on secure pages. It uses a certificate the hub makes on your computer.
- **Camera lean** is off until you turn it on. Only where your head and shoulders are is read, in the browser; the
  video is never shown, recorded, saved or sent.
- **Ride modes (game packs)** run only when signed by the publisher and unchanged since signing. The hub plays a pack
  inside the browser; a pack cannot change the hub itself.

## In scope

The hub's own code in this repository: its local server and pages, pairing, the secure port and certificate, pack
signature checks, the assistant connection (MCP), and how records are stored and shared.

## Out of scope

Services and software the hub works with but doesn't control (Strava, your AI assistant, your watch maker's apps,
the browser and the game engine itself), and setups that expose the hub's ports to the internet. The hub is made for
your home network: **don't forward its ports through your router.**
