from tardis.exceptions.executorexceptions import CommandExecutionFailure
from tardis.utilities.asynccachemap import AsyncCacheMap

from json.decoder import JSONDecodeError
from datetime import datetime
from datetime import timedelta
from functools import partial
from types import MappingProxyType
from unittest import TestCase

import asyncio
import logging


class TestAsyncCacheMap(TestCase):
    def setUp(self):
        self.test_data = {"testA": 123, "testB": "Random String"}
        self.async_cache_map = AsyncCacheMap(update_coroutine=self.update_function)
        self.json_failing_async_cache_map = AsyncCacheMap(
            update_coroutine=self.json_failing_update_function
        )
        self.command_failing_async_cache_map = AsyncCacheMap(
            update_coroutine=self.command_failing_update_function
        )

    async def json_failing_update_function(self):
        raise JSONDecodeError(msg="Bla", doc="Blubb", pos=99)

    async def command_failing_update_function(self):
        raise CommandExecutionFailure(
            message="Failure", stdout="Failure", stderr="Failure", exit_code=2
        )

    async def update_function(self):
        return self.test_data

    def update_status(self):
        asyncio.run(self.async_cache_map.update_status())

    def test_update_async_cache_map(self):
        self.update_status()

    def test_len_async_cache_map(self):
        self.update_status()
        self.assertEqual(len(self.async_cache_map), len(self.test_data))

    def test_get_async_cache_map(self):
        self.update_status()
        self.assertEqual(self.async_cache_map.get("testA"), self.test_data.get("testA"))
        self.assertEqual(self.async_cache_map["testB"], self.test_data["testB"])

    def test_iter_async_cache_map(self):
        self.update_status()

        for key, value in self.async_cache_map.items():
            self.assertEqual(value, self.test_data.get(key))

    def test_json_failing_update(self):
        with self.assertLogs(level=logging.WARNING):
            asyncio.run(self.json_failing_async_cache_map.update_status())
            self.assertEqual(len(self.json_failing_async_cache_map), 0)

    def test_command_failing_update(self):
        with self.assertLogs(level=logging.WARNING):
            asyncio.run(self.json_failing_async_cache_map.update_status())
            self.assertEqual(len(self.json_failing_async_cache_map), 0)

    def test_last_update(self):
        self.assertEqual(self.async_cache_map.last_update, datetime.fromtimestamp(0))
        asyncio.run(self.async_cache_map.update_status())
        self.assertTrue(
            datetime.now() - self.async_cache_map.last_update < timedelta(seconds=1)
        )

    def test_eq_async_cache_map(self):
        test_cache_map = self.async_cache_map
        # Since both objects have been recently initialized, all values (self._max_age,
        # self._last_update, self._data and self._lock) are still the defaults
        self.assertTrue(self.async_cache_map == test_cache_map)

        # Test the opposite
        self.assertFalse(self.async_cache_map != test_cache_map)

    def test_read_only_cache_returns_mappingproxy(self):
        asyncio.run(self.async_cache_map.update_status())  # populate data
        ro_cache = self.async_cache_map.read_only_cache
        self.assertIsInstance(ro_cache, MappingProxyType)
        self.assertEqual(dict(ro_cache), self.async_cache_map._data)

        # Update _data manually and check if read_only_cache reflects changes
        self.async_cache_map._data["new_key"] = "new_value"
        self.assertEqual(ro_cache["new_key"], "new_value")

    def test_read_only_cache_is_immutable(self):
        ro_cache = self.async_cache_map.read_only_cache
        with self.assertRaises(TypeError):
            ro_cache["key"] = "value"  # Attempt to modify should raise TypeError

        with self.assertRaises(TypeError):
            del ro_cache["key"]  # Attempt to delete should raise TypeError

    def test_update_coroutine_returns_original_when_flag_false(self):
        # Ensure the flag is False
        self.assertFalse(self.async_cache_map._provide_cache)
        coro = self.async_cache_map.update_coroutine
        self.assertEqual(coro, self.async_cache_map._update_coroutine)

    def test_update_coroutine_returns_partial_when_flag_true(self):
        # Set the flag to True
        self.async_cache_map._provide_cache = True
        coro = self.async_cache_map.update_coroutine
        self.assertIsInstance(coro, partial)

        # The partial should wrap the original coroutine
        self.assertEqual(coro.func, self.async_cache_map._update_coroutine)

        # The first argument passed should be the read-only cache
        self.assertIsInstance(coro.args[0], MappingProxyType)
        self.assertEqual(coro.args[0], self.async_cache_map.read_only_cache)
