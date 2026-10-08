"""Slow coaching reports must leave telemetry responsive and preserve write order."""
import asyncio, pathlib, sys, time, threading, tempfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import mapserver

async def main():
    bridge = SimpleNamespace(profile={'ftp':180}, workouts=[])
    callbacks = []
    main_thread = threading.get_ident()
    bridge.event = lambda e: callbacks.append((e, threading.get_ident()))
    bridge.refresh_focus = lambda force=False: callbacks.append((force, threading.get_ident()))
    started, finished = threading.Event(), threading.Event()
    order = []
    async def slow(view, method, *args):
        if method == b'GET':
            started.set(); time.sleep(.2)
            view.event('skill evidence'); view.refresh_focus(force=True)
            finished.set(); order.append('read')
            return view.profile['ftp']
        assert finished.is_set(), 'A write must not race a report that persists forecast evidence'
        order.append('write'); return 201
    with patch.object(mapserver, '_coach_api', side_effect=slow):
        read = asyncio.create_task(mapserver.coach_api(bridge,b'GET','/api/coach/today','/api/coach/today',b''))
        ticks = 0
        while not started.is_set(): await asyncio.sleep(.005)
        write = asyncio.create_task(mapserver.coach_api(bridge,b'POST','/api/coach/checkin','/api/coach/checkin',b'{}'))
        while not read.done():
            ticks += 1; await asyncio.sleep(.01)
        assert ticks >= 5, 'Coaching blocked the bike event loop'
        assert await read == 180 and await write == 201 and order == ['read','write']
        assert all(t == main_thread for _, t in callbacks), 'Bridge callbacks ran on a worker'
        started.clear(); finished.clear(); order.clear()
        read = asyncio.create_task(mapserver.coach_api(bridge,b'GET','/api/coach/today','/api/coach/today',b''))
        while not started.is_set(): await asyncio.sleep(.005)
        read.cancel()
        write = asyncio.create_task(mapserver.coach_api(bridge,b'POST','/api/coach/checkin','/api/coach/checkin',b'{}'))
        try: await read
        except asyncio.CancelledError: pass
        else: raise AssertionError('Cancellation was lost')
        assert await write == 201 and order == ['read','write']
    print('PASS slow report allows live ticks; writes serialize; cancellation preserves transaction; callbacks stay on bike loop')

    import loads
    with tempfile.TemporaryDirectory() as tmp:
        count = []
        def summary(base): count.append(base); time.sleep(.04); return {'result':'unchanged model'}
        mapserver._load_cache['key'] = None
        with patch.object(loads,'summary',side_effect=summary), ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(mapserver.load_state,[tmp]*4))
        assert len(count)==1 and all(x==results[0] for x in results)
        mapserver._load_cache['key'] = None
    print('PASS concurrent load reads share a single model calculation')

if __name__ == '__main__': asyncio.run(main())
