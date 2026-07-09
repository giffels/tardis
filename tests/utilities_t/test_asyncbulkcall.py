import asyncio
import time
import sys
from platform import python_implementation
from unittest import TestCase

from tardis.utilities.asyncbulkcall import AsyncBulkCall


class CallCounter:
    def __init__(self, start=0):
        self.calls = start

    async def __call__(self, *tasks):
        this_call = self.calls
        self.calls += 1
        # make *some* runs pause so that this isn't a trivially sequential test
        if this_call % 2:
            await asyncio.sleep(0)
        return [(i, this_call) for i in tasks]


class TestAsyncBulkCall(TestCase):
    @staticmethod
    async def execute(execution: AsyncBulkCall, count: int, delay=None):
        tasks = []
        for i in range(count):
            tasks.append(asyncio.ensure_future(execution(i)))
            if delay is not None:
                await asyncio.sleep(delay)
        return await asyncio.gather(*tasks)

    def test_bulk_size(self):
        """Test that bulks are formed by size"""
        for size in (1, 10, 100, 1000, 2, 3, 5, 7, 97, 2129):
            with self.subTest(size=size):
                execution = AsyncBulkCall(CallCounter(), size=size, delay=0.1)
                result = asyncio.run(self.execute(execution, count=size * 3 + 5))
                self.assertEqual(result, [(i, i // size) for i in range(size * 3 + 5)])

    def test_bulk_delay(self):
        """Test that bulks are formed by delay"""
        test_size, bulk_delay = 1024, 0.1
        # check that delay forces a bulk if the size is too large to be reached
        execution = AsyncBulkCall(CallCounter(), size=2**32, delay=bulk_delay)
        before = time.monotonic()
        result = asyncio.run(self.execute(execution, count=test_size))
        after = time.monotonic()
        # PyPy can have a huge overhead before the JIT has warmed up
        grace = 5 if python_implementation() != "PyPy" else 25
        self.assertLess(after - before, bulk_delay * grace)
        self.assertEqual(result, [(i, 0) for i in range(test_size)])

    def test_delay_tiny(self):
        """Test that a tiny delay cannot stall execution"""
        # sys.float_info.min is not the smallest float possible,
        # but it should be insignificant in all math
        execution = AsyncBulkCall(CallCounter(), size=2**32, delay=sys.float_info.min)
        result = asyncio.run(self.execute(execution, count=2048))
        self.assertEqual(result, [(i, i) for i in range(2048)])

    def test_restart(self):
        """Test that calls work after pausing"""
        asyncio.run(self.check_restart())

    async def check_restart(self):
        bunch_size = 4
        # use large delay to only trigger on size
        execution = AsyncBulkCall(CallCounter(), size=bunch_size // 2, delay=256)
        for repeat in range(6):
            result = await self.execute(execution, bunch_size)
            self.assertEqual(
                result, [(i, i // 2 + repeat * 2) for i in range(bunch_size)]
            )
            await asyncio.sleep(0.01)  # pause to allow for cleanup
            assert execution._dispatch_task is None

    def test_sanity_checks(self):
        """Test against illegal settings"""
        for wrong_size in (0, -1, 0.5, 2j, "15"):
            with self.subTest(size=wrong_size):
                with self.assertRaises(ValueError):
                    AsyncBulkCall(CallCounter(), size=wrong_size, delay=1.0)
        for wrong_delay in (0, -5, 17j, "10"):
            with self.subTest(delay=wrong_delay):
                with self.assertRaises((ValueError, TypeError)):
                    AsyncBulkCall(CallCounter(), size=100, delay=wrong_delay)
        for wrong_concurrency in (0, 2.3, -5, 17j, "10"):
            with self.subTest(delay=wrong_concurrency):
                with self.assertRaises(ValueError):
                    AsyncBulkCall(
                        CallCounter(),
                        size=100,
                        delay=1.0,
                        concurrent=wrong_concurrency,
                    )

    def test_abandoned_queue_cancellation_on_loop_swap(self):
        """
        Test that pending tasks left over from an old loop are safely cleared
        upon a loop swap.
        """
        execution = AsyncBulkCall(CallCounter(), size=100, delay=0.01)

        async def start_and_abandon():
            loop = asyncio.get_running_loop()
            fake_future = loop.create_future()
            # This triggers initialization of self._loop_resources on the first loop
            execution._queue.put_nowait((999, fake_future))

        asyncio.run(start_and_abandon())

        # Verify that the item is sitting stale inside the loop resources queue
        self.assertIsNotNone(execution._loop_resources)
        self.assertFalse(execution._loop_resources.queue.empty())

        # Move to a new event loop execution block
        async def verify_clean_slate():
            task = asyncio.ensure_future(execution(123))
            return await task

        before = time.monotonic()
        result = asyncio.run(verify_clean_slate())
        after = time.monotonic()

        # The execution should be near-instant (well under 0.1s) and warning-free
        self.assertLess(after - before, 0.1)
        self.assertEqual(result, (123, 0))

    def test_concurrency_limit_enforced_and_released(self):
        """
        Test that the concurrency limit works precisely and doesn't freeze due
        to an uncalled release.
        """

        async def slow_command(*tasks):
            await asyncio.sleep(
                0.05
            )  # block execution briefly to stack concurrent bulks
            return [t for t in tasks]

        # Max 2 concurrent execution batches allowed at a time
        execution = AsyncBulkCall(slow_command, size=1, delay=0.1, concurrent=2)

        async def run_test():
            # Send 3 concurrent items. With size=1, they form 3 separate batches.
            # Batch 1 and 2 fill up the concurrency slots (limit=2).
            # Batch 3 will wait until either Batch 1 or 2 finishes and releases
            # its semaphore slot.
            tasks = [asyncio.ensure_future(execution(i)) for i in range(3)]
            return await asyncio.gather(*tasks)

        # If the semaphore release fix works, this returns cleanly.
        # If the fix fails, this would hang indefinitely on the 3rd item.
        result = asyncio.run(run_test())
        self.assertEqual(result, [0, 1, 2])

    def test_multi_loop_reinitialization(self):
        """
        Test that re-using an AsyncBulkCall instance across separate
        `asyncio.run` statements does not hang.
        """
        execution = AsyncBulkCall(CallCounter(), size=5, delay=0.1)

        # Run 1: First event loop lifecycle
        result_1 = asyncio.run(self.execute(execution, count=5))
        self.assertEqual(result_1, [(i, 0) for i in range(5)])

        # Run 2: New event loop lifecycle.
        # This will trigger the dynamic loop check and successfully reset the
        # loop-bound objects
        result_2 = asyncio.run(self.execute(execution, count=5))

        # CallCounter is persistent on the execution instance, so calls are
        # incremented to 1
        self.assertEqual(result_2, [(i, 1) for i in range(5)])
