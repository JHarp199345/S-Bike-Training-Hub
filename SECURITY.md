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
- **Modules (ride modes, game packs)** run only when signed by a trusted publisher and unchanged since signing; see
  [Modules](#modules) below.

## Modules

Modules (ride modes such as Monster Chase) are where a Trojan horse would hide, so the hub treats every module as
untrusted until it proves otherwise.

**Official modules** are signed by the S-Bike Training Hub publisher and sold or shared only through the project's
itch.io page and the games list the hub reads from this repository. Today the hub trusts one publisher key, listed in
[`packs.py`](packs.py) (`TRUSTED_KEYS`), and no other.

**What protects you today**

- **Signature and fingerprints.** Before a module runs, the hub checks that its signature comes from a trusted key and
  that every file matches what was signed. A modified, repackaged or unsigned module is refused, with the reason.
- **No code in the hub.** A module is game data that runs inside the browser. The hub never runs a module's code
  itself, and a module cannot install, add or change anything in the hub.
- **Only listed files.** The hub serves only the files a module's signed list names, of a few allowed kinds, and its
  own page starts the game: a module can't bring its own web page or scripts.

- **Declared access.** The signed manifest names the ride readings and controls a game requests. The installer shows them before approval. The host shares only the declared readings, plus basic connection flags; it never gives the game its session token or a general Hub request interface.
- **Browser isolation.** Pack code runs in an opaque frame with no same-origin permission. Browser requests from that frame cannot reach private Hub routes. The host accepts a small set of validated messages. Camera video stays in the host; a game requesting steering receives only the derived lean value.
- **Bounded controls.** Slope requests are limited and rate checked. An active workout, route or test keeps resistance control. Closing a game revokes its control lease; the existing slope heartbeat flattens resistance if updates stop.

**The current limit.** This is browser isolation, not an operating-system sandbox or a complete outbound-network firewall. The browser and bundled Godot engine remain trusted components. An approved publisher could misuse readings their game is permitted to receive, including through frame navigation. Only the existing official publisher key is accepted; do not treat this as making unknown modules safe. Games currently require a signed permissions declaration and the bundled non-threaded engine.

**Your part**

- Install modules only from the project's itch.io page or the hub's own games list. Never install a module someone
  sends you, and never "fix" a refused module.
- Never add a publisher key to `TRUSTED_KEYS` unless you trust that publisher with everything the hub can see.
- If a module asks for anything beyond a game, or a site offers "free" or "unlocked" versions, report it (below).

**Other publishers.** The hub doesn't accept modules from other publishers yet. If it ever does, it will be only
behind the module sandbox, with each publisher's key added by you, and with the module's abilities shown in plain
words before it installs.

## In scope

The hub's own code in this repository: its local server and pages, pairing, the secure port and certificate, module
signature checks and what modules can reach, the assistant connection (MCP), and how records are stored and shared.
A module that misbehaves, or a way to make the hub run something it should refuse, is in scope.

## Out of scope

Services and software the hub works with but doesn't control (Strava, your AI assistant, your watch maker's apps,
the browser and the game engine itself), and setups that expose the hub's ports to the internet. The hub is made for
your home network: **don't forward its ports through your router.**
