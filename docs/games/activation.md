# Purchased-game activation

Copy the unique key from your itch.io purchase page, paste it in the Ride menu's
module drop area, choose the installed game if prompted, then activate. The key
is not sent anywhere until you approve activation. Do not put it in public issues.

An optional UTF-8 activation file (at most 4 KB) can be dropped instead:

```json
{"format":"s-bike-game-license-1","id":"monster-chase","license_key":"YOUR-KEY"}
```

This file is plain data. The Hub never executes it or follows a URL from it. It
is separate from the publisher-signed shared game ZIP. Keep your real file private.
itch.io's built-in external-key delivery supplies copyable keys; a personalized
downloadable activation file is not currently supplied by the storefront.

For release maintainers: stage packaging/build_package.py with --stage-only, sign
the exact package application files locally, then put the public signed inventory
at packaging/hub-release.json. A full build verifies that inventory and refuses
changed application files. Never add the private signing key to the repository.
The repository checkout has its own hub-release.json; it differs from the package
inventory because packaging adds cli.py and __init__.py.
