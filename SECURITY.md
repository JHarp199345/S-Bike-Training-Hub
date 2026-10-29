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

Modules (ride games such as Monster Chase) are where a Trojan horse would hide, so the hub treats every module as
untrusted until it proves otherwise, and boxes it in even after that.

**Where official modules come from.** Each game has its own GitHub repository, with its code readable there and a
signed download on its releases page. The hub's games list (Ride menu, **Find more modules**) links to them. Today the
hub trusts one publisher key, listed in [`packs.py`](packs.py) (`TRUSTED_KEYS`), and no other.

**Before a game runs**

- **Signature and fingerprints.** The hub checks that the signature comes from a trusted key and that every file
  matches what was signed. A modified, repackaged or unsigned game is refused, with the reason.
- **Only listed files, of a few kinds.** Game data, images, sounds, text. A game can't bring its own web page or
  scripts for the hub to run; the hub's own page starts it on the hub's own engine.
- **Declared access, shown in plain words.** The signed manifest names the ride readings and controls a game wants.
  The installer shows what it **can see**, what it **can control** and what it **cannot** do, before you approve.

**What you can check yourself**

- **The code is readable.** A game's scripts and shaders are packed as plain text, unencrypted, and published in its
  repository. Anyone can open the download and compare.
- **`web-code.txt`** in every download lists each line where the game runs web code in its frame (Godot's
  `JavaScriptBridge`): the whole conversation between the game and the hub page, in one place.
- **Only art is encrypted.** Models, textures and sounds bought or downloaded under licences that forbid handing out
  the files are encrypted inside the download. No code may live in an encrypted file: the packing tool refuses any
  scene or resource with code inside it.

**While a game runs**

- **Its own walled-off site.** On the computer running the hub, a game runs on its own name
  (`<game>.game.localhost`); elsewhere in an opaque frame. Either way the browser keeps it away from the hub's pages,
  data and login, and from other games.
- **No web requests.** The game's security policy lets it load only its own signed files and the engine. Peer
  connections (WebRTC) are blocked where the browser supports it, and link prefetching is off.
- **No other pages.** If a game's frame ever loads a second page (a way to carry readings out in a web address), the
  hub ends its connection and takes it off the screen.
- **No devices or personal data.** Camera, microphone, location, USB, Bluetooth, MIDI, motion sensors, screen
  capture, clipboard, payments and passkeys are all denied to the game. Camera lean runs in the hub's page; the game
  gets only the lean number.
- **Only what it declared.** The host passes only the declared readings, plus basic connection flags, and never the
  hub's session token or a general way to make hub requests.
- **Bounded controls.** Slope requests are limited and rate checked. An active workout, route or test keeps
  resistance control. Closing a game revokes its control; the slope heartbeat flattens resistance if updates stop.

**The honest limits.** This is browser isolation, not an operating-system sandbox. The browser and the bundled Godot
engine are trusted components. If a game navigates away, the hub stops it, but that first navigation has already
been sent; so a malicious game could leak, once, the readings it was granted (power, cadence and so on), never your
files, history or account. Only the official publisher key is accepted; this does not make unknown modules safe.

**Your part**

- Install modules only from a game's own GitHub page or the hub's games list. Never install a module someone sends
  you, and never "fix" a refused module.
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
