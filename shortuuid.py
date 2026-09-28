"""shortuuid.py - make bless advertise standard Bluetooth services by their
16-bit codes.

bless hands CoreBluetooth the full 128-bit string it was given. For a standard
service like Cycling Power, "00001818-0000-1000-8000-00805f9b34fb", CoreBluetooth
then treats it as a 16-byte custom UUID instead of the 2-byte code 0x1818 - and a
watch or Kinomap filtering its sensor search on 0x1818 never lists the device.
(Verified: CBUUID.UUIDWithString_ gives 16 bytes for the long form, 2 for "1818".)

This patch gives CoreBluetooth the short form and keeps every Python-side lookup
on the long form, so the rest of bless works unchanged. Import it before
creating a BlessServer.
"""
import uuid as _uuid

from CoreBluetooth import CBUUID

import bless.backends.corebluetooth.characteristic as _char
import bless.backends.corebluetooth.descriptor as _desc
import bless.backends.corebluetooth.server as _cbserver
import bless.backends.corebluetooth.service as _svc
import bless.backends.server as _server

BASE = "-0000-1000-8000-00805f9b34fb"


def short(s: str) -> str:
    s = str(s)
    low = s.lower()
    if len(low) == 36 and low.startswith("0000") and low.endswith(BASE):
        return s[4:8].upper()
    return s


def long(s: str) -> str:
    s = str(s)
    if len(s) == 4:
        return f"0000{s.lower()}{BASE}"
    if len(s) == 8:
        return f"{s.lower()}{BASE}"
    return s.lower()


class _ShortCBUUID:
    """Stands in for CBUUID where bless builds services and characteristics."""

    class _Init:
        def initWithString_(self, s):
            return CBUUID.UUIDWithString_(short(s))

    @classmethod
    def alloc(cls):
        return cls._Init()

    UUIDWithString_ = staticmethod(lambda s: CBUUID.UUIDWithString_(short(s)))


def _UUID(s):
    """bless normalises lookups with str(UUID(x)); accept the short form too."""
    return _uuid.UUID(long(s))


for mod in (_char, _desc, _svc):
    mod.CBUUID = _ShortCBUUID
for mod in (_server, _cbserver):
    mod.UUID = _UUID


def _service_uuid(self):
    if self._cb_service is not None:
        return long(self._cb_service.UUID().UUIDString())
    return long(self._uuid)


_svc.BlessGATTServiceCoreBluetooth.uuid = property(_service_uuid)
