"""Shared-memory frame transport for zero-copy inter-filter image handoff."""
import os
from multiprocessing import shared_memory

SHM_NSLOTS = max(2, int(os.environ.get('OPENFILTER_SHM_NSLOTS', '4')))
SHM_SLOT_SIZE = int(os.environ.get('OPENFILTER_SHM_SLOT_SIZE', str(32 * 1024 * 1024)))  # 32MB default


def shm_enabled() -> bool:
    return os.environ.get('OPENFILTER_SHM_ENABLE', '').strip().lower() in ('1', 'true', 'yes', 'on')


class SHMPool:
    """Sender-side pool of named SHM segments with round-robin allocation."""
    # Round-robin reuse is safe only because the ZMQ send->recv pipeline loop is SYNCHRONOUS:
    # the sender blocks on its next send until the receiver has consumed the prior frame, so
    # the sender cannot lap the receiver within SHM_NSLOTS frames. If the runtime ever adopts
    # async/pipelined dispatch, this invariant breaks and a generation counter or semaphore
    # would be needed to gate slot reuse.

    def __init__(self, prefix: str, nslots: int = SHM_NSLOTS, slot_size: int = SHM_SLOT_SIZE):
        self.prefix = prefix
        self.nslots = nslots
        self.slot_size = slot_size
        self.slots: list[shared_memory.SharedMemory] = []
        self._idx = 0

        for i in range(nslots):
            name = f'{prefix}-{i}'
            # Sweep stale segments from prior crashed runs
            try:
                stale = shared_memory.SharedMemory(name=name, create=False)
                stale.close()
                stale.unlink()
            except FileNotFoundError:
                pass
            self.slots.append(shared_memory.SharedMemory(name=name, create=True, size=slot_size))

    def put(self, src: memoryview) -> tuple[str, int]:
        """Copy src into the next slot and return (slot_name, nbytes)."""
        nbytes = len(src)
        if nbytes > self.slot_size:
            raise ValueError(f'frame payload {nbytes} bytes exceeds SHM slot size {self.slot_size}; increase OPENFILTER_SHM_SLOT_SIZE')
        slot = self.slots[self._idx % self.nslots]
        self._idx += 1
        slot.buf[:nbytes] = src
        return (slot.name, nbytes)

    def destroy(self):
        for slot in self.slots:
            try:
                slot.close()
            except BufferError:
                pass  # outstanding memoryview; unmaps at process exit
            try:
                slot.unlink()
            except FileNotFoundError:
                pass
        self.slots.clear()


class SHMAttachCache:
    """Receiver-side cache that lazily attaches SHM segments by name."""

    def __init__(self):
        self._cache: dict[str, shared_memory.SharedMemory] = {}

    def get(self, name: str) -> shared_memory.SharedMemory:
        if name not in self._cache:
            self._cache[name] = shared_memory.SharedMemory(name=name, create=False)
        return self._cache[name]

    def destroy(self):
        for shm in self._cache.values():
            try:
                shm.close()
            except BufferError:
                pass  # numpy views still hold a reference; the mmap unmaps at process exit
        self._cache.clear()
