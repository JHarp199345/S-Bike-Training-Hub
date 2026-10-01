"""Bound a native Bluetooth constructor that can otherwise block the web server."""
import asyncio
import threading


async def construct(factory, timeout=15):
    loop = asyncio.get_running_loop()
    result = loop.create_future()

    def deliver(value, error):
        if result.done():
            return
        if error is not None:
            result.set_exception(error)
        else:
            result.set_result(value)

    def worker():
        try:
            value, error = factory(), None
        except Exception as exc:
            value, error = None, exc
        try:
            loop.call_soon_threadsafe(deliver, value, error)
        except RuntimeError:
            pass  # app closed while the native Bluetooth callback was still waiting

    # Daemon: native powered-on wait cannot strand process shutdown.
    threading.Thread(target=worker, name='Hub Bluetooth startup', daemon=True).start()
    return await asyncio.wait_for(result, timeout)
