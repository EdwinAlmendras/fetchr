import asyncio
import time

class TimeLocker:
    def __init__(self, interval: float):
        self.interval = interval
        self._last_time = 0.0
        self._lock = asyncio.Lock()

    async def wait(self):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_time
            remaining = self.interval - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_time = time.monotonic()