#!/usr/bin/env python3
"""scan.py - find the bike and list what it speaks over Bluetooth.

Run with the bike awake (pedal a few turns) and NOT connected to the phone
or the watch, since it only holds one connection at a time.

    .venv/bin/python scan.py            # list nearby devices, then inspect the bike
    .venv/bin/python scan.py --listen   # also print 15 s of live bike data
"""
import argparse
import asyncio

from bleak import BleakClient, BleakScanner

# Standard Bluetooth fitness services, so the output reads in plain words.
KNOWN = {
    "00001826": "Fitness Machine (FTMS)",
    "00001818": "Cycling Power",
    "00001816": "Cycling Speed and Cadence",
    "0000180d": "Heart Rate",
    "0000180a": "Device Information",
    "0000180f": "Battery",
    "00002ad2": "Indoor Bike Data",
    "00002acc": "Fitness Machine Feature",
    "00002ad9": "Fitness Machine Control Point",
    "00002ada": "Fitness Machine Status",
    "00002ad6": "Supported Resistance Range",
    "00002ad8": "Supported Power Range",
    "00002a63": "Cycling Power Measurement",
    "00002a5b": "CSC Measurement",
}
FITNESS = ("00001826", "00001818", "00001816")


def label(uuid):
    return KNOWN.get(uuid[:8].lower(), "")


def parse_indoor_bike_data(data: bytes) -> dict:
    """Decode the FTMS Indoor Bike Data characteristic (0x2AD2)."""
    flags = int.from_bytes(data[0:2], "little")
    i, out = 2, {}

    def take(n, signed=False):
        nonlocal i
        v = int.from_bytes(data[i:i + n], "little", signed=signed)
        i += n
        return v

    if not flags & 0x0001:
        out["speed_kmh"] = take(2) / 100
    if flags & 0x0002:
        take(2)  # average speed
    if flags & 0x0004:
        out["cadence_rpm"] = take(2) / 2
    if flags & 0x0008:
        take(2)  # average cadence
    if flags & 0x0010:
        out["distance_m"] = take(3)
    if flags & 0x0020:
        out["resistance"] = take(2, signed=True)
    if flags & 0x0040:
        out["power_w"] = take(2, signed=True)
    if flags & 0x0080:
        take(2, signed=True)  # average power
    if flags & 0x0100:
        take(2); take(2); take(1)  # energy
    if flags & 0x0200:
        out["hr_bpm"] = take(1)
    return out


async def main(listen: bool):
    print("Scanning 10 s ...")
    found = await BleakScanner.discover(timeout=10, return_adv=True)
    bikes = []
    for dev, adv in sorted(found.values(), key=lambda x: -(x[1].rssi or -999)):
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        fit = [label(u) for u in uuids if u[:8] in FITNESS]
        if fit or (dev.name and any(k in dev.name.upper() for k in ("MERACH", "S29", "BIKE", "MR"))):
            bikes.append(dev)
            print(f"  * {dev.name!r:<24} rssi {adv.rssi:>4}  {', '.join(fit) or 'name match'}")
    if not bikes:
        print("No bike found. Pedal to wake it, make sure the phone and watch are not "
              "connected to it, and run again.")
        return

    bike = bikes[0]
    print(f"\nConnecting to {bike.name!r} ...")
    async with BleakClient(bike) as client:
        for svc in client.services:
            print(f"\nSERVICE {svc.uuid}  {label(svc.uuid)}")
            for ch in svc.characteristics:
                print(f"   char {ch.uuid}  {label(ch.uuid):<32} {','.join(ch.properties)}")
                if "read" in ch.properties and svc.uuid[:8].lower() == "0000180a":
                    try:
                        v = await client.read_gatt_char(ch)
                        print(f"        = {v.decode(errors='replace')}")
                    except Exception:
                        pass

        if listen:
            ibd = next((c for s in client.services for c in s.characteristics
                        if c.uuid[:8].lower() == "00002ad2"), None)
            if not ibd:
                print("\nNo Indoor Bike Data characteristic; the bike is not plain FTMS.")
                return
            print("\nListening 15 s. Pedal.")
            await client.start_notify(ibd, lambda _, d: print("  ", parse_indoor_bike_data(d)))
            await asyncio.sleep(15)
            await client.stop_notify(ibd)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", action="store_true")
    asyncio.run(main(ap.parse_args().listen))
