from tardis.utilities.pipeline import PipelineProcessor
from tardis.utilities.pipeline import StopProcessing

from unittest import TestCase

import asyncio


class TestPipelineProcessor(TestCase):
    def setUp(self):
        async def test_update(pipeline_input, drone):
            self.assertEqual(pipeline_input, 10)
            self.assertEqual(drone, "drone_place_holder")
            return 1

        self.pipeline_processor = PipelineProcessor([test_update])

    def test_pipeline_processor(self):
        self.assertEqual(
            asyncio.run(
                self.pipeline_processor.run_pipeline(
                    pipeline_input=10,
                    drone="drone_place_holder",
                )
            ),
            1,
        )

    def test_add_function(self):
        async def test_add(pipeline_input, drone):
            self.assertEqual(pipeline_input, 1)
            self.assertEqual(drone, "drone_place_holder")
            return 2

        self.pipeline_processor.add_to_pipeline(test_add)
        self.assertEqual(
            asyncio.run(
                self.pipeline_processor.run_pipeline(
                    pipeline_input=10,
                    drone="drone_place_holder",
                )
            ),
            2,
        )

    def test_stop_processing(self):
        def test_stop_processing(pipeline_input, drone):
            self.assertEqual(pipeline_input, 10)
            self.assertEqual(drone, "drone_place_holder")
            raise StopProcessing(last_result=99)

        pipeline_processor = PipelineProcessor([test_stop_processing])
        self.assertEqual(
            asyncio.run(
                pipeline_processor.run_pipeline(
                    pipeline_input=10,
                    drone="drone_place_holder",
                )
            ),
            99,
        )
