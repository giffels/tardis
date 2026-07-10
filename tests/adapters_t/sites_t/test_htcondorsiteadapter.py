from tardis.adapters.sites.htcondor import HTCondorAdapter
from tardis.exceptions.executorexceptions import CommandExecutionFailure
from tardis.exceptions.tardisexceptions import TardisError
from tardis.exceptions.tardisexceptions import TardisResourceStatusUpdateFailed
from tardis.interfaces.siteadapter import ResourceStatus
from tardis.utilities.attributedict import AttributeDict
from tests.utilities.utilities import mock_executor_run_command


from unittest import TestCase
from unittest.mock import patch

import asyncio
import logging

CONDOR_SUBMIT_OUTPUT = """Submitting job(s)
** Proc 1351043.0:
Args = "150"
ClusterId = 1351043
Cmd = "start_pilot.sh"
CommittedSlotTime = 0
CommittedSuspensionTime = 0
CommittedTime = 0
CompletionDate = 0
CondorPlatform = "$CondorPlatform: x86_64_CentOS7 $"
CondorVersion = "$CondorVersion: 9.0.4 Jul 29 2021 BuildID: 552036 PackageID: 9.0.4-1 $"
EnteredCurrentStatus = 1641297637
JobStatus = 1
JobUniverse = 5
MyType = "Job"
Owner = undefined
ProcId = 0
QDate = 1641297637
Rank = 0.0
RequestCpus = 8
RequestDisk = 167772160
RequestMemory = 32768
"""

CONDOR_Q_OUTPUT_IDLE = "1\t1351043\t0"
CONDOR_Q_OUTPUT_RUN = "2\t1351043\t0"
CONDOR_Q_OUTPUT_REMOVING = "3\t1351043\t0"
CONDOR_Q_OUTPUT_COMPLETED = "4\t1351043\t0"
CONDOR_Q_OUTPUT_HELD = "5\t1351043\t0"
CONDOR_Q_OUTPUT_TRANSFERING_OUTPUT = "6\t1351043\t0"
CONDOR_Q_OUTPUT_SUSPENDED = "7\t1351043\t0"
CONDOR_Q_OUTPUT_DOES_NOT_EXISTS = "1\t1351042\t0"

CONDOR_RM_OUTPUT = "Job 1351043.0 marked for removal"
CONDOR_RM_FAILED_OUTPUT = "Job 1351043.0 not found"
CONDOR_RM_FAILED_MESSAGE = "Run command condor_rm 1351043.0 via ShellExecutor failed"

CONDOR_SUSPEND_OUTPUT = """Job 1351043.0 suspended"""
CONDOR_SUSPEND_FAILED_OUTPUT_NOT_FOUND = """Job 1351043.0 not found"""
CONDOR_SUSPEND_FAILED_OUTPUT_NOT_RUNNING = (
    """Job 1351043.0 not running to be suspended"""
)
CONDOR_SUSPEND_FAILED_MESSAGE = """Run command condor_suspend 1351043 via
ShellExecutor failed"""

CONDOR_SUBMIT_JDL_CONDOR_OBS = """executable = start_pilot.sh
transfer_input_files = setup_pilot.sh
output = logs/$(cluster).$(process).out
error = logs/$(cluster).$(process).err
log = logs/cluster.log

accounting_group=tardis

environment=TardisDroneCores=8;TardisDroneMemory=32768;TardisDroneDisk=167772160;TardisDroneUuid=test-123

request_cpus=8
request_memory=32768
request_disk=167772160

queue 1"""  # noqa: B950

CONDOR_SUBMIT_PER_ARGUMENTS_JDL_CONDOR_OBS = """executable = start_pilot.sh
arguments=--cores=8 --memory=32768 --disk=167772160 --uuid=test-123
transfer_input_files = setup_pilot.sh
output = logs/$(cluster).$(process).out
error = logs/$(cluster).$(process).err
log = logs/cluster.log

accounting_group=tardis

request_cpus=8
request_memory=32768
request_disk=167772160

queue 1"""  # noqa: B950

CONDOR_SUBMIT_JDL_SPARK_OBS = """executable = start_pilot.sh
transfer_input_files = setup_pilot.sh
output = logs/$(cluster).$(process).out
error = logs/$(cluster).$(process).err
log = logs/cluster.log

accounting_group=tardis

environment=TardisDroneCores=8;TardisDroneMemory=32;TardisDroneDisk=160;TardisDroneUuid=test-123

request_cpus=8
request_memory=32768
request_disk=167772160

queue 1"""  # noqa: B950


class TestHTCondorSiteAdapter(TestCase):
    mock_config_patcher = None
    mock_executor_patcher = None

    @classmethod
    def setUpClass(cls):
        cls.mock_config_patcher = patch("tardis.interfaces.siteadapter.Configuration")
        cls.mock_config = cls.mock_config_patcher.start()
        cls.mock_executor_patcher = patch(
            "tardis.adapters.sites.htcondor.ShellExecutor"
        )
        cls.mock_executor = cls.mock_executor_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_config_patcher.stop()
        cls.mock_executor_patcher.stop()

    def setUp(self):
        config = self.mock_config.return_value
        test_site_config = config.TestSite
        test_site_config.MachineMetaData = self.machine_meta_data
        test_site_config.MachineTypeConfiguration = self.machine_type_configuration
        test_site_config.executor = self.mock_executor.return_value
        test_site_config.bulk_size = 100
        test_site_config.bulk_delay = 0.01
        test_site_config.max_age = 10

        self.adapter = HTCondorAdapter(machine_type="test2large", site_name="TestSite")

    @property
    def machine_meta_data(self):
        return AttributeDict(
            test2large=AttributeDict(Cores=8, Memory=32, Disk=160),
            test2large_args=AttributeDict(Cores=8, Memory=32, Disk=160),
            test2large_deprecated=AttributeDict(Cores=8, Memory=32, Disk=160),
            testunkownresource=AttributeDict(Cores=8, Memory=32, Disk=160, Foo=3),
            testsubmitoptions=AttributeDict(Cores=8, Memory=32, Disk=160),
        )

    @property
    def machine_type_configuration(self):
        return AttributeDict(
            test2large=AttributeDict(jdl="tests/data/submit.jdl"),
            test2large_args=AttributeDict(jdl="tests/data/submit_per_arguments.jdl"),
            test2large_deprecated=AttributeDict(jdl="tests/data/submit_deprecated.jdl"),
            testunkownresource=AttributeDict(jdl="tests/data/submit.jdl"),
            testsubmitoptions=AttributeDict(
                jdl="tests/data/submit.jdl",
                SubmitOptions=AttributeDict(pool="my_remote_pool", spool=None),
            ),
        )

    @mock_executor_run_command(
        [
            AttributeDict(stdout=CONDOR_SUBMIT_OUTPUT),
        ]
        * 5
    )
    def test_deploy_resource_htcondor_obs(self):
        response = asyncio.run(
            self.adapter.deploy_resource(
                AttributeDict(
                    drone_uuid="test-123",
                    obs_machine_meta_data_translation_mapping=AttributeDict(
                        Cores=1,
                        Memory=1024,
                        Disk=1024 * 1024,
                    ),
                ),
            ),
        )
        self.assertEqual(response.remote_resource_uuid, "1351043.0")

        _, kwargs = self.mock_executor.return_value.run_command.call_args
        self.assertEqual(
            kwargs["stdin_input"],
            CONDOR_SUBMIT_JDL_CONDOR_OBS,
        )

        self.mock_executor.reset()

        asyncio.run(
            self.adapter.deploy_resource(
                AttributeDict(
                    drone_uuid="test-123",
                    obs_machine_meta_data_translation_mapping=AttributeDict(
                        Cores=1,
                        Memory=1,
                        Disk=1,
                    ),
                ),
            ),
        )

        _, kwargs = self.mock_executor.return_value.run_command.call_args
        self.assertEqual(
            kwargs["stdin_input"],
            CONDOR_SUBMIT_JDL_SPARK_OBS,
        )
        self.mock_executor.reset()

        self.adapter = HTCondorAdapter(
            machine_type="test2large_deprecated", site_name="TestSite"
        )

        # "queue 1" deprecation
        with self.assertWarns(FutureWarning):
            asyncio.run(
                self.adapter.deploy_resource(
                    AttributeDict(
                        drone_uuid="test-123",
                        obs_machine_meta_data_translation_mapping=AttributeDict(
                            Cores=1, Memory=1, Disk=1
                        ),
                    ),
                ),
            )
        self.mock_executor.reset()

        self.adapter = HTCondorAdapter(
            machine_type="test2large_args", site_name="TestSite"
        )

        asyncio.run(
            self.adapter.deploy_resource(
                AttributeDict(
                    drone_uuid="test-123",
                    obs_machine_meta_data_translation_mapping=AttributeDict(
                        Cores=1,
                        Memory=1024,
                        Disk=1024 * 1024,
                    ),
                ),
            ),
        )

        _, kwargs = self.mock_executor.return_value.run_command.call_args
        self.assertEqual(
            kwargs["stdin_input"],
            CONDOR_SUBMIT_PER_ARGUMENTS_JDL_CONDOR_OBS,
        )
        self.mock_executor.reset()

        self.adapter = HTCondorAdapter(
            machine_type="testsubmitoptions", site_name="TestSite"
        )

        # Test support for submit options
        asyncio.run(
            self.adapter.deploy_resource(
                AttributeDict(
                    drone_uuid="test-123",
                    obs_machine_meta_data_translation_mapping=AttributeDict(
                        Cores=1,
                        Memory=1024,
                        Disk=1024 * 1024,
                    ),
                ),
            ),
        )

        args, _ = self.mock_executor.return_value.run_command.call_args
        self.assertEqual(
            "condor_submit -verbose -maxjobs 1 -pool my_remote_pool -spool", args[0]
        )

    def test_translate_resources_raises_logs(self):
        self.adapter = HTCondorAdapter(
            machine_type="testunkownresource", site_name="TestSite"
        )
        with self.assertLogs(logging.getLogger(), logging.ERROR):
            with self.assertRaises(KeyError):
                asyncio.run(
                    self.adapter.deploy_resource(
                        AttributeDict(
                            drone_uuid="test-123",
                            obs_machine_meta_data_translation_mapping=AttributeDict(
                                Cores=1,
                                Memory=1024,
                                Disk=1024 * 1024,
                            ),
                        ),
                    ),
                )

    def test_machine_meta_data(self):
        self.assertEqual(
            self.adapter.machine_meta_data, self.machine_meta_data.test2large
        )

    def test_machine_type(self):
        self.assertEqual(self.adapter.machine_type, "test2large")

    def test_site_name(self):
        self.assertEqual(self.adapter.site_name, "TestSite")

    @mock_executor_run_command(
        [
            AttributeDict(stdout=CONDOR_Q_OUTPUT_IDLE),
        ]
    )
    def test_resource_status_idle(self):
        response = asyncio.run(
            self.adapter.resource_status(
                AttributeDict(remote_resource_uuid="1351043.0")
            ),
        )
        self.assertEqual(response.resource_status, ResourceStatus.Booting)

    @mock_executor_run_command(
        [
            AttributeDict(stdout=CONDOR_Q_OUTPUT_RUN),
        ]
    )
    def test_resource_status_run(self):
        response = asyncio.run(
            self.adapter.resource_status(
                AttributeDict(remote_resource_uuid="1351043.0")
            ),
        )
        self.assertEqual(response.resource_status, ResourceStatus.Running)

    @mock_executor_run_command(
        [
            AttributeDict(stdout=CONDOR_Q_OUTPUT_REMOVING),
        ]
    )
    def test_resource_status_removing(self):
        response = asyncio.run(
            self.adapter.resource_status(
                AttributeDict(remote_resource_uuid="1351043.0")
            ),
        )
        self.assertEqual(response.resource_status, ResourceStatus.Running)

    @mock_executor_run_command(
        [
            AttributeDict(stdout=CONDOR_Q_OUTPUT_COMPLETED),
        ]
    )
    def test_resource_status_completed(self):
        response = asyncio.run(
            self.adapter.resource_status(
                AttributeDict(remote_resource_uuid="1351043.0")
            ),
        )
        self.assertEqual(response.resource_status, ResourceStatus.Deleted)

    @mock_executor_run_command(
        [
            AttributeDict(stdout=CONDOR_Q_OUTPUT_HELD),
        ]
    )
    def test_resource_status_held(self):
        response = asyncio.run(
            self.adapter.resource_status(
                AttributeDict(remote_resource_uuid="1351043.0")
            ),
        )
        self.assertEqual(response.resource_status, ResourceStatus.Error)

    @mock_executor_run_command(
        [
            AttributeDict(stdout=CONDOR_Q_OUTPUT_TRANSFERING_OUTPUT),
        ]
    )
    def test_resource_status_transfering_output(self):
        response = asyncio.run(
            self.adapter.resource_status(
                AttributeDict(remote_resource_uuid="1351043.0")
            ),
        )
        self.assertEqual(response.resource_status, ResourceStatus.Running)

    @mock_executor_run_command(
        [
            AttributeDict(stdout=CONDOR_Q_OUTPUT_SUSPENDED),
        ]
    )
    def test_resource_status_unexpanded(self):
        response = asyncio.run(
            self.adapter.resource_status(
                AttributeDict(remote_resource_uuid="1351043.0")
            ),
        )
        self.assertEqual(response.resource_status, ResourceStatus.Stopped)

    @mock_executor_run_command(
        [
            CommandExecutionFailure(
                message="Failed", stdout="Failed", stderr="Failed", exit_code=2
            ),
        ]
    )
    def test_resource_status_command_execution_error(self):
        with self.assertLogs(level=logging.WARNING):
            with self.assertRaises(CommandExecutionFailure):
                asyncio.run(
                    self.adapter.resource_status(
                        AttributeDict(
                            remote_resource_uuid="1351043.0",
                        )
                    ),
                )

    @mock_executor_run_command(
        [
            AttributeDict(stdout=CONDOR_Q_OUTPUT_DOES_NOT_EXISTS),
        ]
    )
    def test_resource_status_already_deleted(self):
        response = asyncio.run(
            self.adapter.resource_status(
                AttributeDict(remote_resource_uuid="1351043.0")
            ),
        )
        self.assertEqual(response.resource_status, ResourceStatus.Deleted)

    @mock_executor_run_command(
        [
            AttributeDict(stdout=CONDOR_SUSPEND_OUTPUT),
        ]
    )
    def test_stop_resource(self):
        response = asyncio.run(
            self.adapter.stop_resource(AttributeDict(remote_resource_uuid="1351043.0"))
        )
        self.assertIsNone(response)

    @mock_executor_run_command(
        [
            CommandExecutionFailure(
                message=CONDOR_SUSPEND_FAILED_MESSAGE,
                exit_code=1,
                stderr=CONDOR_SUSPEND_FAILED_OUTPUT_NOT_FOUND,
                stdout="",
                stdin="",
            ),
        ]
    )
    def test_stop_resource_failed_redo_not_found(self):
        with self.assertRaises(TardisResourceStatusUpdateFailed):
            asyncio.run(
                self.adapter.stop_resource(
                    AttributeDict(remote_resource_uuid="1351043.0")
                ),
            )

    @mock_executor_run_command(
        [
            CommandExecutionFailure(
                message=CONDOR_SUSPEND_FAILED_MESSAGE,
                exit_code=1,
                stderr=CONDOR_SUSPEND_FAILED_OUTPUT_NOT_RUNNING,
                stdout="",
                stdin="",
            ),
        ]
    )
    def test_stop_resource_failed_redo_not_running(self):
        with self.assertRaises(TardisResourceStatusUpdateFailed):
            asyncio.run(
                self.adapter.stop_resource(
                    AttributeDict(remote_resource_uuid="1351043.0")
                ),
            )

    @mock_executor_run_command(
        [
            CommandExecutionFailure(
                message=CONDOR_SUSPEND_FAILED_MESSAGE,
                exit_code=2,
                stderr=CONDOR_SUSPEND_FAILED_OUTPUT_NOT_FOUND,
                stdout="",
                stdin="",
            ),
        ]
    )
    def test_stop_resource_failed_raise(self):
        with self.assertRaises(CommandExecutionFailure):
            asyncio.run(
                self.adapter.stop_resource(
                    AttributeDict(remote_resource_uuid="1351043.0")
                ),
            )

    @mock_executor_run_command(
        [
            AttributeDict(stdout=CONDOR_RM_OUTPUT),
        ]
    )
    def test_terminate_resource(self):
        response = asyncio.run(
            self.adapter.terminate_resource(
                AttributeDict(remote_resource_uuid="1351043.0")
            ),
        )
        self.assertIsNone(response)

    @mock_executor_run_command(
        [
            AttributeDict(stdout=CONDOR_RM_FAILED_OUTPUT),
        ]
    )
    def test_terminate_resource_failed_redo(self):
        with self.assertRaises(TardisResourceStatusUpdateFailed):
            asyncio.run(
                self.adapter.terminate_resource(
                    AttributeDict(remote_resource_uuid="1351043.0")
                ),
            )

    @mock_executor_run_command(
        [
            CommandExecutionFailure(
                message=CONDOR_RM_FAILED_MESSAGE,
                exit_code=2,
                stderr=CONDOR_RM_FAILED_OUTPUT,
                stdout="",
                stdin="",
            ),
        ]
    )
    def test_terminate_resource_failed_raise(self):
        with self.assertRaises(CommandExecutionFailure):
            asyncio.run(
                self.adapter.terminate_resource(
                    AttributeDict(remote_resource_uuid="1351043.0")
                ),
            )

    def test_exception_handling(self):
        def test_exception_handling(raise_it, catch_it):
            with self.assertRaises(catch_it):
                with self.adapter.handle_exceptions():
                    raise raise_it

        matrix = [
            (Exception, TardisError),
            (TardisResourceStatusUpdateFailed, TardisResourceStatusUpdateFailed),
        ]

        for to_raise, to_catch in matrix:
            test_exception_handling(to_raise, to_catch)
