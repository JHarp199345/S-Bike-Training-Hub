#!/usr/bin/env python3
"""adtest.py - does this Mac actually advertise? Minimal power-meter broadcast,
with every CoreBluetooth message printed. Run from a terminal with Bluetooth
permission; stop with Ctrl+C."""
import asyncio
import logging
import sys

import shortuuid  # noqa: F401  (must load before bless servers are built)
from bless import BlessServer, GATTAttributePermissions as Perm, GATTCharacteristicProperties as Prop

CPS = "00001818-0000-1000-8000-00805f9b34fb"
CP_MEAS = "00002a63-0000-1000-8000-00805f9b34fb"
NAME = sys.argv[1] if len(sys.argv) > 1 else "S29 Test"


async def main():
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    loop = asyncio.get_running_loop()
    s = BlessServer(name=NAME, loop=loop)
    s.read_request_func = lambda c, **_: bytearray(b"\x00")
    s.write_request_func = lambda c, v, **_: None
    await s.add_gatt({CPS: {CP_MEAS: {"Properties": Prop.notify, "Permissions": Perm.readable, "Value": None}}})
    await s.start()
    pm = s.peripheral_manager_delegate.peripheral_manager
    for _ in range(600):
        subs = s.get_characteristic(CP_MEAS).obj.subscribedCentrals()
        print(f"state={pm.state()} (5=on)  advertising={pm.isAdvertising()}  subscribers={len(subs) if subs else 0}",
              flush=True)
        await asyncio.sleep(3)


asyncio.run(main())
