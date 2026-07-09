from tardis.adapters.sites.slurm import SlurmAdapter
from tardis.exceptions.tardisexceptions import TardisError
from tardis.exceptions.tardisexceptions import TardisTimeout
from tardis.exceptions.tardisexceptions import TardisResourceStatusUpdateFailed
from tardis.exceptions.executorexceptions import CommandExecutionFailure
from tardis.interfaces.siteadapter import ResourceStatus
from tardis.utilities.attributedict import AttributeDict
from tests.utilities.utilities import mock_executor_run_command

from unittest import TestCase
from unittest.mock import MagicMock, patch

from warnings import filterwarnings

import asyncio
import logging

__all__ = ["TestSlurmAdapter"]

TEST_RESOURCE_STATUS_RESPONSE = """
1390065||PENDING
1391999|fh2n1573|TIMEOUT
1391999.batch|fh2n1573|CANCELLED
"""

TEST_RESOURCE_STATUS_RESPONSE_RUNNING = """
1390065|fh2n1552|RUNNING
1390065.batch|fh2n1552|RUNNING
1391999|fh2n1573|TIMEOUT
1391999.batch|fh2n1573|CANCELLED
"""

TEST_RESOURCE_STATUS_RESPONSE_ALL_STATES = """
1000000|fh1n1000|BOOT_FAIL
1001000|fh1n1001|CANCELLED
1002000|fh1n1002|COMPLETED
1003000|fh1n1003|CONFIGURING
1004000|fh1n1004|COMPLETING
1005000|fh1n1005|DEADLINE
1006000|fh1n1006|FAILED
1007000|fh1n1007|NODE_FAIL
1008000|fh1n1008|OUT_OF_MEMORY
1009000||PENDING
1010000|fh1n1010|PREEMPTED
1011000|fh1n1011|RUNNING
1012000|fh1n1012|RESV_DEL_HOLD
1013000|fh1n1013|REQUEUE_FED
1014000|fh1n1014|REQUEUE_HOLD
1015000|fh1n1015|REQUEUED
1016000|fh1n1016|RESIZING
1017000|fh1n1017|REVOKED
1018000|fh1n1018|SIGNALING
1019000|fh1n1019|SPECIAL_EXIT
1020000|fh1n1020|STAGE_OUT
1021000|fh1n1021|STOPPED
1022000|fh1n1022|SUSPENDED
1023000|fh1n1023|TIMEOUT
"""

TEST_DEPLOY_RESOURCE_RESPONSE = """
Submitted batch job 1390065
"""


class TestSlurmAdapter(TestCase):
    mock_config_patcher = None
    mock_executor_patcher = None

    @classmethod
    def setUpClass(cls):
        cls.mock_config_patcher = patch("tardis.interfaces.siteadapter.Configuration")
        cls.mock_config = cls.mock_config_patcher.start()
        cls.mock_executor_patcher = patch("tardis.adapters.sites.slurm.ShellExecutor")
        cls.mock_executor = cls.mock_executor_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_config_patcher.stop()
        cls.mock_executor_patcher.stop()

    def setUp(self):
        config = self.mock_config.return_value
        config.TestSite = MagicMock(
            spec=[
                "MachineMetaData",
                "StatusUpdate",
                "MachineTypeConfiguration",
                "executor",
            ]
        )
        self.test_site_config = config.TestSite
        self.test_site_config.MachineMetaData = self.machine_meta_data
        self.test_site_config.StatusUpdate = 10
        self.test_site_config.MachineTypeConfiguration = self.machine_type_configuration
        self.test_site_config.executor = self.mock_executor.return_value
        # set to smallest positive float
        # prevents BulkCall from blocking indefinitely on _get_bulk() when
        # the event loop is closed before the semaphore is released by asyncio.run
        self.test_site_config.bulk_delay = 0.01  # sys.float_info.min

        self.slurm_adapter = SlurmAdapter(
            machine_type="test2large", site_name="TestSite"
        )

    def tearDown(self):
        pass

    @property
    def machine_meta_data(self):
        return AttributeDict(test2large=AttributeDict(Cores=20, Memory=62, Disk=100))

    @property
    def machine_type_configuration(self):
        return AttributeDict(
            test2large=AttributeDict(
                Partition="normal", StartupCommand="pilot.sh", Walltime="60"
            )
        )

    @property
    def resource_attributes(self):
        return AttributeDict(
            machine_type="test2large",
            site_name="TestSite",
            remote_resource_uuid=1390065,
            resource_status=ResourceStatus.Booting,
            drone_uuid="testsite-1390065",
        )

    def test_start_up_command_deprecation_warning(self):
        # Necessary to avoid annoying message in PyCharm
        filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)
        del self.test_site_config.MachineTypeConfiguration.test2large.StartupCommand

        with self.assertRaises(AttributeError):
            self.slurm_adapter = SlurmAdapter(
                machine_type="test2large", site_name="TestSite"
            )

        self.test_site_config.StartupCommand = "pilot.sh"

        with self.assertWarns(DeprecationWarning):
            self.slurm_adapter = SlurmAdapter(
                machine_type="test2large", site_name="TestSite"
            )

    @mock_executor_run_command(TEST_DEPLOY_RESOURCE_RESPONSE)
    def test_deploy_resource(self):
        resource_attributes = AttributeDict(
            machine_type="test2large",
            site_name="TestSite",
            obs_machine_meta_data_translation_mapping=AttributeDict(
                Cores=1,
                Memory=1024,
                Disk=1024,
            ),
            drone_uuid="testsite-1390065",
        )

        self.assertDictEqual(
            AttributeDict(
                remote_resource_uuid=1390065, resource_status=ResourceStatus.Booting
            ),
            asyncio.run(self.slurm_adapter.deploy_resource(resource_attributes)),
        )

        self.mock_executor.return_value.run_command.assert_called_with(
            "sbatch -p normal -N 1 -n 20 -t 60 --mem=63488mb --export=SLURM_Walltime=60,TardisDroneCores=20,TardisDroneMemory=63488,TardisDroneDisk=102400,TardisDroneUuid=testsite-1390065 pilot.sh"  # noqa: B950
        )

        self.mock_executor.reset_mock()

        self.test_site_config.MachineMetaData.test2large.Memory = 2.5

        asyncio.run(self.slurm_adapter.deploy_resource(resource_attributes))

        self.mock_executor.return_value.run_command.assert_called_with(
            "sbatch -p normal -N 1 -n 20 -t 60 --mem=2560mb --export=SLURM_Walltime=60,TardisDroneCores=20,TardisDroneMemory=2560,TardisDroneDisk=102400,TardisDroneUuid=testsite-1390065 pilot.sh"  # noqa: B950
        )

        self.mock_executor.reset_mock()

        self.test_site_config.MachineMetaData.test2large.Memory = 2.546372129

        asyncio.run(self.slurm_adapter.deploy_resource(resource_attributes))

        self.mock_executor.return_value.run_command.assert_called_with(
            "sbatch -p normal -N 1 -n 20 -t 60 --mem=2607mb --export=SLURM_Walltime=60,TardisDroneCores=20,TardisDroneMemory=2607,TardisDroneDisk=102400,TardisDroneUuid=testsite-1390065 pilot.sh"  # noqa: B950
        )

    @mock_executor_run_command(TEST_DEPLOY_RESOURCE_RESPONSE)
    def test_deploy_resource_w_submit_options(self):
        self.test_site_config.MachineTypeConfiguration.test2large.SubmitOptions = (
            AttributeDict(long=AttributeDict(gres="tmp:1G"))
        )

        slurm_adapter = SlurmAdapter(machine_type="test2large", site_name="TestSite")

        asyncio.run(
            slurm_adapter.deploy_resource(
                resource_attributes=AttributeDict(
                    machine_type="test2large",
                    site_name="TestSite",
                    obs_machine_meta_data_translation_mapping=AttributeDict(
                        Cores=1,
                        Memory=1000,
                        Disk=1000,
                    ),
                    drone_uuid="testsite-1390065",
                ),
            )
        )

        self.mock_executor.return_value.run_command.assert_called_with(
            "sbatch -p normal -N 1 -n 20 -t 60 --gres=tmp:1G --mem=63488mb --export=SLURM_Walltime=60,TardisDroneCores=20,TardisDroneMemory=62000,TardisDroneDisk=100000,TardisDroneUuid=testsite-1390065 pilot.sh"  # noqa: B950
        )

    def test_machine_meta_data(self):
        self.assertEqual(
            self.slurm_adapter.machine_meta_data, self.machine_meta_data["test2large"]
        )

    def test_machine_type(self):
        self.assertEqual(self.slurm_adapter.machine_type, "test2large")

    def test_site_name(self):
        self.assertEqual(self.slurm_adapter.site_name, "TestSite")

    @mock_executor_run_command(TEST_RESOURCE_STATUS_RESPONSE)
    def test_resource_status(self):
        self.assertDictEqual(
            AttributeDict(
                resource_status=ResourceStatus.Booting, remote_resource_uuid=1390065
            ),
            asyncio.run(
                self.slurm_adapter.resource_status(
                    resource_attributes=self.resource_attributes,
                ),
            ),
        )

        self.mock_executor.return_value.run_command.assert_called_with(
            'squeue -o "%A|%N|%T" -h -t all --job=1390065'
        )

    @mock_executor_run_command(TEST_RESOURCE_STATUS_RESPONSE)
    def test_resource_status_w_options(self):
        self.test_site_config.MachineTypeConfiguration.test2large.StatusOptions = (
            AttributeDict(
                long=AttributeDict(cluster="cm4"),
                short=AttributeDict(p="cm4_tiny"),
            )
        )

        slurm_adapter = SlurmAdapter(machine_type="test2large", site_name="TestSite")

        self.assertDictEqual(
            AttributeDict(
                resource_status=ResourceStatus.Booting, remote_resource_uuid=1390065
            ),
            asyncio.run(
                slurm_adapter.resource_status(
                    resource_attributes=self.resource_attributes,
                ),
            ),
        )

        self.mock_executor.return_value.run_command.assert_called_with(
            'squeue -p cm4_tiny --cluster=cm4 -o "%A|%N|%T" -h -t all --job=1390065'
        )

    @mock_executor_run_command(TEST_RESOURCE_STATUS_RESPONSE_RUNNING)
    def test_update_resource_status(self):
        self.assertEqual(
            self.resource_attributes["resource_status"], ResourceStatus.Booting
        )

        self.assertDictEqual(
            AttributeDict(
                resource_status=ResourceStatus.Running, remote_resource_uuid=1390065
            ),
            asyncio.run(
                self.slurm_adapter.resource_status(
                    resource_attributes=self.resource_attributes,
                ),
            ),
        )

        self.mock_executor.return_value.run_command.assert_called_with(
            'squeue -o "%A|%N|%T" -h -t all --job=1390065'
        )

    @mock_executor_run_command(TEST_RESOURCE_STATUS_RESPONSE_ALL_STATES)
    def test_resource_state_translation(self):
        state_translations = {
            "BOOT_FAIL": ResourceStatus.Error,
            "CANCELLED": ResourceStatus.Deleted,
            "COMPLETED": ResourceStatus.Deleted,
            "CONFIGURING": ResourceStatus.Booting,
            "COMPLETING": ResourceStatus.Running,
            "DEADLINE": ResourceStatus.Error,
            "FAILED": ResourceStatus.Error,
            "NODE_FAIL": ResourceStatus.Error,
            "OUT_OF_MEMORY": ResourceStatus.Error,
            "PENDING": ResourceStatus.Booting,
            "PREEMPTED": ResourceStatus.Deleted,
            "RUNNING": ResourceStatus.Running,
            "RESV_DEL_HOLD": ResourceStatus.Stopped,
            "REQUEUE_FED": ResourceStatus.Booting,
            "REQUEUE_HOLD": ResourceStatus.Booting,
            "REQUEUED": ResourceStatus.Booting,
            "RESIZING": ResourceStatus.Running,
            "REVOKED": ResourceStatus.Error,
            "SIGNALING": ResourceStatus.Running,
            "SPECIAL_EXIT": ResourceStatus.Booting,
            "STAGE_OUT": ResourceStatus.Running,
            "STOPPED": ResourceStatus.Stopped,
            "SUSPENDED": ResourceStatus.Stopped,
            "TIMEOUT": ResourceStatus.Deleted,
        }

        for id, value in enumerate(state_translations.values()):
            job_id = int(f"{id + 1000}000")
            returned_resource_attributes = asyncio.run(
                self.slurm_adapter.resource_status(
                    AttributeDict(remote_resource_uuid=job_id),
                )
            )
            self.assertEqual(returned_resource_attributes.resource_status, value)

            self.assertTrue(self.mock_executor.return_value.run_command.called)

            self.mock_executor.return_value.run_command.assert_called_with(
                f'squeue -o "%A|%N|%T" -h -t all --job={job_id}'
            )

            self.mock_executor.reset_mock()

    @mock_executor_run_command("")
    def test_resource_status_of_completed_jobs_w_empty_reply(self):
        response = asyncio.run(
            self.slurm_adapter.resource_status(
                AttributeDict(
                    resource_id="1390065",
                    remote_resource_uuid="1351043",
                ),
            )
        )

        self.assertEqual(response.resource_status, ResourceStatus.Deleted)

        self.mock_executor.return_value.run_command.assert_called_with(
            'squeue -o "%A|%N|%T" -h -t all --job=1351043'
        )

    @mock_executor_run_command(
        stdout="",
        raise_exception=CommandExecutionFailure(
            message="Run command squeue --job=1351043 via SSHExecutor failed",
            stdout="",
            stderr="slurm_load_jobs error: Invalid job id specified",
            exit_code=1,
        ),
    )
    def test_resource_status_of_completed_jobs_w_raised_exception(self):
        response = asyncio.run(
            self.slurm_adapter.resource_status(
                AttributeDict(
                    resource_id="1390065",
                    remote_resource_uuid="1351043",
                ),
            )
        )

        self.assertEqual(response.resource_status, ResourceStatus.Deleted)

        self.mock_executor.return_value.run_command.assert_called_with(
            'squeue -o "%A|%N|%T" -h -t all --job=1351043'
        )

        # test that exception is re-raised if two or more job ids are specified,
        # since Slurm does not fail in that case.

        tasks = [
            self.slurm_adapter.resource_status(
                AttributeDict(
                    resource_id="1390065",
                    remote_resource_uuid="1351043",
                ),
            ),
            self.slurm_adapter.resource_status(
                AttributeDict(
                    resource_id="1390066",
                    remote_resource_uuid="1351044",
                ),
            ),
        ]

        async def run_gather():
            return await asyncio.gather(*tasks)

        with self.assertLogs(level=logging.WARNING):
            with self.assertRaises(CommandExecutionFailure):
                asyncio.run(run_gather())

        self.mock_executor.return_value.run_command.assert_called_with(
            'squeue -o "%A|%N|%T" -h -t all --job=1351043,1351044'
        )

    @mock_executor_run_command(
        stdout="",
        raise_exception=CommandExecutionFailure(
            message="Failed", stdout="Failed", stderr="Failed", exit_code=2
        ),
    )
    def test_resource_status_update_failed(self):
        with self.assertLogs(level=logging.WARNING):
            with self.assertRaises(CommandExecutionFailure):
                asyncio.run(
                    self.slurm_adapter.resource_status(
                        AttributeDict(remote_resource_uuid="1390065"),
                    )
                )

        self.mock_executor.return_value.run_command.assert_called_with(
            'squeue -o "%A|%N|%T" -h -t all --job=1390065'
        )

    @mock_executor_run_command(stdout="", stderr="", exit_code=0)
    def test_stop_resource(self):
        asyncio.run(
            self.slurm_adapter.stop_resource(
                resource_attributes=self.resource_attributes,
            )
        )

        self.mock_executor.return_value.run_command.assert_called_with(
            "scancel 1390065"
        )

    @mock_executor_run_command(stdout="", stderr="", exit_code=0)
    def test_terminate_resource(self):
        asyncio.run(
            self.slurm_adapter.terminate_resource(
                resource_attributes=self.resource_attributes,
            )
        )

        self.mock_executor.return_value.run_command.assert_called_with(
            "scancel 1390065"
        )

    @mock_executor_run_command(stdout="", stderr="", exit_code=0)
    def test_terminate_resource_w_options(self):
        self.test_site_config.MachineTypeConfiguration.test2large.TerminateOptions = (
            AttributeDict(
                long=AttributeDict(cluster="cm4"),
                short=AttributeDict(p="cm4_tiny"),
            )
        )

        slurm_adapter = SlurmAdapter(machine_type="test2large", site_name="TestSite")

        asyncio.run(
            slurm_adapter.terminate_resource(
                resource_attributes=self.resource_attributes,
            )
        )

        self.mock_executor.return_value.run_command.assert_called_with(
            "scancel -p cm4_tiny --cluster=cm4 1390065"
        )

    def test_exception_handling(self):
        def test_exception_handling(to_raise, to_catch):
            with self.assertRaises(to_catch):
                with self.assertLogs(level=logging.WARNING):
                    with self.slurm_adapter.handle_exceptions():
                        raise to_raise

        matrix = [
            (asyncio.TimeoutError(), TardisTimeout),
            (
                CommandExecutionFailure(
                    message="Test", exit_code=255, stdout="Test", stderr="Test"
                ),
                TardisResourceStatusUpdateFailed,
            ),
            (TardisResourceStatusUpdateFailed, TardisResourceStatusUpdateFailed),
            (Exception, TardisError),
        ]

        for to_raise, to_catch in matrix:
            test_exception_handling(to_raise, to_catch)
