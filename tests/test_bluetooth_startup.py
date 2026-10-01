import asyncio, pathlib, sys, threading
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from bluetooth_startup import construct

async def main():
    assert await construct(lambda: 'ready', .5) == 'ready'
    def bad():raise ValueError('denied')
    try:await construct(bad,.5)
    except ValueError:pass
    else:raise AssertionError('native error lost')
    release=threading.Event(); ticks=[]
    async def heartbeat():
        for i in range(4):
            await asyncio.sleep(.01);ticks.append(i)
    task=asyncio.create_task(heartbeat())
    try:
        await construct(lambda:release.wait(),.06)
    except TimeoutError:pass
    else:raise AssertionError('native wait was not bounded')
    finally:release.set()
    await task
    assert len(ticks)==4, 'native constructor blocked the web event loop'
    await asyncio.sleep(.01) # late result must not set a cancelled future
asyncio.run(main())
print('ALL PASS: Bluetooth success, error, timeout, responsive event loop and late callback')
