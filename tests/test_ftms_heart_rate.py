"""The bike's heart rate, read from FTMS Indoor Bike Data and kept on the ride (2026-10-27): the games' HUD shows it."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from bridge import Ride, parse_indoor_bike_data  # noqa: E402


def packet(flags, *fields):
    b = flags.to_bytes(2, "little")
    for value, size in fields:
        b += int(value).to_bytes(size, "little", signed=False)
    return b


def test_speed_packet_with_heart_rate():
    # speed present (bit 0 clear), heart rate (bit 9)
    out = parse_indoor_bike_data(packet(0x0200, (2850, 2), (142, 1)))
    assert out == {"speed_kmh": 28.5, "heart_rate": 142}


def test_heart_rate_after_average_power_and_energy():
    # cadence, power, average power, expended energy (2+2+1), heart rate - read in FTMS order
    flags = 0x0001 | 0x0004 | 0x0040 | 0x0080 | 0x0100 | 0x0200
    out = parse_indoor_bike_data(packet(flags, (180, 2), (210, 2), (205, 2), (55, 2), (600, 2), (9, 1), (151, 1)))
    assert out["cadence_rpm"] == 90 and out["power_w"] == 210 and out["heart_rate"] == 151


def test_no_heart_rate_flag_no_reading():
    assert "heart_rate" not in parse_indoor_bike_data(packet(0x0000, (2000, 2)))


def test_ride_keeps_heart_rate_and_rejects_nonsense():
    r = Ride(2096)
    assert r.heart_rate == 0
    r.update({"speed_kmh": 20.0, "heart_rate": 138})
    assert r.heart_rate == 138
    r.update({"speed_kmh": 20.0, "heart_rate": 255})        # a dropped sensor's junk: keep the last good value
    assert r.heart_rate == 138


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
