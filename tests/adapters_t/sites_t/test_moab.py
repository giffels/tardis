from tardis.adapters.sites.moab import MoabAdapter
from tardis.exceptions.executorexceptions import CommandExecutionFailure
from tardis.exceptions.tardisexceptions import TardisError
from tardis.exceptions.tardisexceptions import TardisTimeout
from tardis.exceptions.tardisexceptions import TardisResourceStatusUpdateFailed
from tardis.interfaces.siteadapter import ResourceStatus
from tardis.utilities.attributedict import AttributeDict
from tests.utilities.utilities import mock_executor_run_command

from unittest import TestCase
from unittest.mock import MagicMock, call, patch

from datetime import datetime
from warnings import filterwarnings

import asyncio
import asyncssh
import logging

__all__ = ["TestMoabAdapter"]

TEST_RESOURCE_STATUS_RESPONSE = """
<Data>
 <Object>queue</Object>
 <cluster LocalActiveNodes="68" LocalAllocProcs="1360" LocalConfigNodes="1037" LocalIdleNodes="7" LocalIdleProcs="7192" LocalUpNodes="922" LocalUpProcs="18432" RemoteActiveNodes="0" RemoteAllocProcs="0" RemoteConfigNodes="0" RemoteIdleNodes="0" RemoteIdleProcs="0" RemoteUpNodes="0" RemoteUpProcs="0" time="1553503935"/>
 <queue count="68" option="active">
  <job AWDuration="140875" Account="bw16g013" DRMJID="5096381.mg1.nemo.privat" EEDuration="44150" GJID="5096381" Group="ka_etp" JobID="5096381" JobName="startVM.py" MasterHost="n4545.nemo.privat" PAL="torque" ReqAWDuration="172800" ReqProcs="20" RsvStartTime="1553362801" RunPriority="-43322" StartPriority="-43322" StartTime="1553362801" StatPSDed="2813667.000000" StatPSUtl="140642.124800" State="Running" SubmissionTime="1553318572" SuspendDuration="0" User="ka_qb1555"/>
 </queue>
 <queue count="20" option="eligible">
  <job Account="bw16g013" EEDuration="72423" GJID="4761849" Group="ka_etp" JobID="4761849" JobName="startVM.py" ReqAWDuration="172800" ReqProcs="20" StartPriority="-38601" StartTime="0" State="Idle" SubmissionTime="1553431244" SuspendDuration="0" User="ka_qb1555"/>
 </queue>
 <queue count="0" option="blocked"/>
</Data><Data>
 <Object>queue</Object>
 <cluster LocalActiveNodes="0" LocalAllocProcs="0" LocalConfigNodes="1037" LocalIdleNodes="1" LocalIdleProcs="5895" LocalUpNodes="922" LocalUpProcs="18432" RemoteActiveNodes="0" RemoteAllocProcs="0" RemoteConfigNodes="0" RemoteIdleNodes="0" RemoteIdleProcs="0" RemoteUpNodes="0" RemoteUpProcs="0" time="1553521152"/>
 <queue count="1" option="completed" purgetime="86400">
  <job AWDuration="169164" Account="bw16g013" Class="compute" CompletionCode="0" CompletionTime="1553436477" DRMJID="5087810.mg1.nemo.privat" EEDuration="1457" GJID="5087810" Group="ka_etp" JobID="5087810" JobName="startVM.py" MasterHost="n4250.nemo.privat" PAL="torque" ReqAWDuration="172800" ReqNodes="1" ReqProcs="20" StartTime="1553267313" StatPSDed="3383282.000000" StatPSUtl="168401.142000" State="Completed" SubmissionTime="1553265273" SuspendDuration="0" User="ka_qb1555"/>
 </queue>
</Data>

"""  # noqa: B950

TEST_RESOURCE_STATUS_RESPONSE_RUNNING = """
<Data>
 <Object>queue</Object>
 <cluster LocalActiveNodes="2" LocalAllocProcs="40" LocalConfigNodes="1038" LocalIdleNodes="5" LocalIdleProcs="555" LocalUpNodes="917" LocalUpProcs="18320" RemoteActiveNodes="0" RemoteAllocProcs="0" RemoteConfigNodes="0" RemoteIdleNodes="0" RemoteIdleProcs="0" RemoteUpNodes="0" RemoteUpProcs="0" time="1551959144"/>
 <queue count="2" option="active">
  <job AWDuration="80173" Account="bw16g013" DRMJID="4986904.mg1.nemo.privat" EEDuration="7575" GJID="4761849" Group="ka_etp" JobID="4761849" JobName="startVM.py" MasterHost="n3559.nemo.privat" PAL="torque" ReqAWDuration="172800" ReqProcs="20" RsvStartTime="1551878897" RunPriority="-43174" StartPriority="-43174" StartTime="1551878897" StatPSDed="1603250.600000" StatPSUtl="80162.530000" State="Running" SubmissionTime="1551871257" SuspendDuration="0" User="ka_qb1555"/>
  <job AWDuration="35418" Account="bw16g013" DRMJID="4989355.mg1.nemo.privat" EEDuration="1831" GJID="4761850" Group="ka_etp" JobID="4761850" JobName="startVM.py" MasterHost="n4131.nemo.privat" PAL="torque" ReqAWDuration="172800" ReqProcs="20" RsvStartTime="1551923652" RunPriority="-44134" StartPriority="-44134" StartTime="1551923652" StatPSDed="708148.200000" StatPSUtl="35407.410000" State="Running" SubmissionTime="1551921753" SuspendDuration="0" User="ka_qb1555"/>
 </queue>
 <queue count="0" option="eligible"/>
 <queue count="0" option="blocked"/>
</Data><Data>
 <Object>queue</Object>
 <cluster LocalActiveNodes="0" LocalAllocProcs="0" LocalConfigNodes="1037" LocalIdleNodes="1" LocalIdleProcs="5895" LocalUpNodes="922" LocalUpProcs="18432" RemoteActiveNodes="0" RemoteAllocProcs="0" RemoteConfigNodes="0" RemoteIdleNodes="0" RemoteIdleProcs="0" RemoteUpNodes="0" RemoteUpProcs="0" time="1553521152"/>
 <queue count="1" option="completed" purgetime="86400">
  <job AWDuration="169164" Account="bw16g013" Class="compute" CompletionCode="0" CompletionTime="1553436477" DRMJID="5087810.mg1.nemo.privat" EEDuration="1457" GJID="5087810" Group="ka_etp" JobID="5087810" JobName="startVM.py" MasterHost="n4250.nemo.privat" PAL="torque" ReqAWDuration="172800" ReqNodes="1" ReqProcs="20" StartTime="1553267313" StatPSDed="3383282.000000" StatPSUtl="168401.142000" State="Completed" SubmissionTime="1553265273" SuspendDuration="0" User="ka_qb1555"/>
 </queue>
</Data>

"""  # noqa: B950

TEST_DEPLOY_RESOURCE_RESPONSE = """

4761849
"""

TEST_TERMINATE_RESOURCE_RESPONSE = """

job '4761849' cancelled

"""

TEST_TIMEOUT_RESPONSE = """
ERROR:  client timed out after 30 seconds (hostname:port=mg1.nemo.privat:42559)
"""

TEST_TERMINATE_DEAD_RESOURCE_RESPONSE = """
ERROR:  invalid job specified (4761849)

"""

STATE_TRANSLATIONS = [
    ("BatchHold", ResourceStatus.Stopped),
    ("Canceling", ResourceStatus.Running),
    ("CANCELLED", ResourceStatus.Deleted),
    ("Completed", ResourceStatus.Deleted),
    ("COMPLETED", ResourceStatus.Deleted),
    ("COMPLETING", ResourceStatus.Running),
    ("Deffered", ResourceStatus.Booting),
    ("Depend", ResourceStatus.Error),
    ("Dependency", ResourceStatus.Error),
    ("FAILED", ResourceStatus.Error),
    ("Idle", ResourceStatus.Booting),
    ("JobHeldUser", ResourceStatus.Stopped),
    ("Migrated", ResourceStatus.Booting),
    ("NODE_FAIL", ResourceStatus.Error),
    ("NotQueued", ResourceStatus.Error),
    ("PENDING", ResourceStatus.Booting),
    ("Priority", ResourceStatus.Booting),
    ("Removed", ResourceStatus.Deleted),
    ("Resources", ResourceStatus.Booting),
    ("Running", ResourceStatus.Running),
    ("RUNNING", ResourceStatus.Running),
    ("Staging", ResourceStatus.Booting),
    ("Starting", ResourceStatus.Booting),
    ("Suspended", ResourceStatus.Stopped),
    ("SUSPENDED", ResourceStatus.Stopped),
    ("SystemHold", ResourceStatus.Stopped),
    ("TimeLimit", ResourceStatus.Deleted),
    ("TIMEOUT", ResourceStatus.Deleted),
    ("UserHold", ResourceStatus.Stopped),
    ("Vacated", ResourceStatus.Deleted),
]

TEST_RESOURCE_STATE_TRANSLATION_RESPONSE = "\n\n".join(f"""
<Data>
 <Object>queue</Object>
 <cluster LocalActiveNodes="0" LocalAllocProcs="0" LocalConfigNodes="918" LocalIdleNodes="9" LocalIdleProcs="1336" LocalUpNodes="916" LocalUpProcs="18776" RemoteActiveNodes="0" RemoteAllocProcs="0" RemoteConfigNodes="0" RemoteIdleNodes="0" RemoteIdleProcs="0" RemoteUpNodes="0" RemoteUpProcs="0" time="1583334681"/>
 <queue count="0" option="active"/>
 <queue count="0" option="eligible"/>
 <queue count="0" option="blocked"/>
</Data>

<Data>
 <Object>queue</Object>
 <cluster LocalActiveNodes="0" LocalAllocProcs="0" LocalConfigNodes="918" LocalIdleNodes="9" LocalIdleProcs="1336" LocalUpNodes="916" LocalUpProcs="18776" RemoteActiveNodes="0" RemoteAllocProcs="0" RemoteConfigNodes="0" RemoteIdleNodes="0" RemoteIdleProcs="0" RemoteUpNodes="0" RemoteUpProcs="0" time="1583334681"/>
 <queue count="1" option="completed" purgetime="86400">
  <job Account="bw16g013" CompletionCode="CNCLD" EEDuration="2729" GJID="76242{num:02}" Group="ka_etp" JobID="76242{num:02}" JobName="startVM.py" ReqAWDuration="360" ReqProcs="20" StartTime="0" StatPSDed="0.000000" StatPSUtl="0.000000" State="{resource_status}" SubmissionTime="1583331813" SuspendDuration="0" User="ka_qb1555"/>
 </queue>
</Data>
""" for num, (resource_status, _) in enumerate(STATE_TRANSLATIONS))  # noqa: B950


class TestMoabAdapter(TestCase):
    mock_config_patcher = None
    mock_executor_patcher = None

    @classmethod
    def setUpClass(cls):
        cls.mock_config_patcher = patch("tardis.interfaces.siteadapter.Configuration")
        cls.mock_config = cls.mock_config_patcher.start()
        cls.mock_executor_patcher = patch("tardis.adapters.sites.moab.ShellExecutor")
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
        self.test_site_config.bulk_delay = 0.01

        self.moab_adapter = MoabAdapter(machine_type="test2large", site_name="TestSite")

    def tearDown(self):
        pass

    @property
    def machine_meta_data(self):
        return AttributeDict(test2large=AttributeDict(Cores=128, Memory=120, Disk=100))

    @property
    def machine_type_configuration(self):
        return AttributeDict(
            test2large=AttributeDict(
                NodeType="1:ppn=20", StartupCommand="startVM.py", Walltime="02:00:00:00"
            )
        )

    @property
    def resource_attributes(self):
        return AttributeDict(
            machine_type="test2large",
            site_name="TestSite",
            remote_resource_uuid=4761849,
            resource_status=ResourceStatus.Booting,
            created=datetime.strptime(
                "Wed Jan 23 2019 15:01:47", "%a %b %d %Y %H:%M:%S"
            ),
            updated=datetime.strptime(
                "Wed Jan 23 2019 15:02:17", "%a %b %d %Y %H:%M:%S"
            ),
            drone_uuid="testsite-abcdef",
            obs_machine_meta_data_translation_mapping=AttributeDict(
                Cores=1,
                Memory=1,
                Disk=1,
            ),
        )

    def test_start_up_command_deprecation_warning(self):
        # Necessary to avoid annoying message in PyCharm
        filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)
        del self.test_site_config.MachineTypeConfiguration.test2large.StartupCommand

        with self.assertRaises(AttributeError):
            self.moab_adapter = MoabAdapter(
                machine_type="test2large", site_name="TestSite"
            )

        self.test_site_config.StartupCommand = "startVM.py"

        with self.assertWarns(DeprecationWarning):
            self.moab_adapter = MoabAdapter(
                machine_type="test2large", site_name="TestSite"
            )

    @mock_executor_run_command(TEST_DEPLOY_RESOURCE_RESPONSE)
    def test_deploy_resource(self):
        self.assertDictEqual(
            AttributeDict(
                remote_resource_uuid=4761849, resource_status=ResourceStatus.Booting
            ),
            asyncio.run(
                self.moab_adapter.deploy_resource(
                    resource_attributes=self.resource_attributes,
                )
            ),
        )

        self.mock_executor.return_value.run_command.assert_called_with(
            "msub -j oe -m p -l walltime=02:00:00:00,mem=120gb,nodes=1:ppn=20 -v TardisDroneCores=128,TardisDroneMemory=120,TardisDroneDisk=100,TardisDroneUuid=testsite-abcdef startVM.py"  # noqa: B950
        )

    @mock_executor_run_command(TEST_DEPLOY_RESOURCE_RESPONSE)
    def test_deploy_resource_w_submit_options(self):
        self.test_site_config.MachineTypeConfiguration.test2large.SubmitOptions = (
            AttributeDict(
                short=AttributeDict(M="someone@somewhere.com"),
                long=AttributeDict(timeout=60),
            )
        )

        asyncio.run(
            self.moab_adapter.deploy_resource(
                resource_attributes=self.resource_attributes,
            )
        )

        self.mock_executor.return_value.run_command.assert_called_with(
            "msub -M someone@somewhere.com -j oe -m p -l walltime=02:00:00:00,mem=120gb,nodes=1:ppn=20 -v TardisDroneCores=128,TardisDroneMemory=120,TardisDroneDisk=100,TardisDroneUuid=testsite-abcdef --timeout=60 startVM.py"  # noqa: B950
        )

    def test_machine_meta_data(self):
        self.assertEqual(
            self.moab_adapter.machine_meta_data, self.machine_meta_data["test2large"]
        )

    def test_machine_type(self):
        self.assertEqual(self.moab_adapter.machine_type, "test2large")

    def test_site_name(self):
        self.assertEqual(self.moab_adapter.site_name, "TestSite")

    @mock_executor_run_command(TEST_RESOURCE_STATUS_RESPONSE)
    def test_resource_status(self):
        self.assertDictEqual(
            AttributeDict(
                remote_resource_uuid=4761849, resource_status=ResourceStatus.Booting
            ),
            asyncio.run(
                self.moab_adapter.resource_status(
                    resource_attributes=self.resource_attributes,
                )
            ),
        )

    @mock_executor_run_command(TEST_RESOURCE_STATE_TRANSLATION_RESPONSE)
    def test_resource_state_translation(self):
        self.mock_executor.reset_mock()
        for num, (_, state) in enumerate(STATE_TRANSLATIONS):
            job_id = f"76242{num:02}"
            return_resource_attributes = asyncio.run(
                self.moab_adapter.resource_status(
                    AttributeDict(remote_resource_uuid=job_id),
                )
            )
            self.assertEqual(return_resource_attributes.resource_status, state)

            self.mock_executor.return_value.run_command.assert_has_calls(
                [
                    call("showq --xml -w user=${USER}"),
                    call("showq -c --xml -w user=${USER}"),
                ]
            )
            self.mock_executor.reset_mock()

    @mock_executor_run_command(TEST_RESOURCE_STATUS_RESPONSE_RUNNING)
    def test_resource_status_update(self):
        self.assertEqual(
            self.resource_attributes["resource_status"], ResourceStatus.Booting
        )

        self.assertDictEqual(
            AttributeDict(
                remote_resource_uuid=4761849, resource_status=ResourceStatus.Running
            ),
            asyncio.run(
                self.moab_adapter.resource_status(
                    resource_attributes=self.resource_attributes,
                )
            ),
        )

    @mock_executor_run_command(TEST_TERMINATE_RESOURCE_RESPONSE)
    def test_stop_resource(self):
        asyncio.run(
            self.moab_adapter.stop_resource(
                resource_attributes=self.resource_attributes,
            )
        )
        self.mock_executor.return_value.run_command.assert_called_with(
            "canceljob 4761849"
        )

    @mock_executor_run_command(TEST_TERMINATE_RESOURCE_RESPONSE)
    def test_terminate_resource(self):
        asyncio.run(
            self.moab_adapter.terminate_resource(
                resource_attributes=self.resource_attributes,
            )
        )
        self.mock_executor.return_value.run_command.assert_called_with(
            "canceljob 4761849"
        )

    @mock_executor_run_command(
        "",
        stderr=TEST_TERMINATE_DEAD_RESOURCE_RESPONSE,
        exit_code=1,
        raise_exception=CommandExecutionFailure(
            message="Test",
            stdout="",
            stderr=TEST_TERMINATE_DEAD_RESOURCE_RESPONSE,
            exit_code=1,
        ),
    )
    def test_terminate_dead_resource(self):
        with self.assertLogs(level=logging.WARNING):
            asyncio.run(
                self.moab_adapter.terminate_resource(
                    resource_attributes=self.resource_attributes,
                )
            )

    @mock_executor_run_command(
        "",
        exit_code=2,
        raise_exception=CommandExecutionFailure(
            message="Test", stdout="", stderr="", exit_code=2
        ),
    )
    def test_terminate_resource_error(self):
        with self.assertRaises(CommandExecutionFailure):
            asyncio.run(
                self.moab_adapter.terminate_resource(
                    resource_attributes=self.resource_attributes,
                )
            )

    @mock_executor_run_command(
        stdout="",
        raise_exception=CommandExecutionFailure(
            message="Failed", stdout="Failed", stderr="Failed", exit_code=2
        ),
    )
    def test_resource_status_update_failed(self):
        with self.assertRaises(CommandExecutionFailure):
            asyncio.run(
                self.moab_adapter.resource_status(
                    AttributeDict(
                        resource_id=1351043,
                        remote_resource_uuid=1351043,
                        resource_state=ResourceStatus.Booting,
                    ),
                )
            )

    @mock_executor_run_command(TEST_RESOURCE_STATUS_RESPONSE_RUNNING)
    def test_resource_status_of_completed_jobs(self):
        response = asyncio.run(
            self.moab_adapter.resource_status(
                AttributeDict(
                    resource_id=1390065,
                    remote_resource_uuid=1351043,
                ),
            )
        )
        self.assertEqual(response.resource_status, ResourceStatus.Deleted)

    def test_exception_handling(self):
        def test_exception_handling(to_raise, to_catch):
            with self.assertRaises(to_catch):
                with self.assertLogs(level=logging.WARNING):
                    with self.moab_adapter.handle_exceptions():
                        raise to_raise

        matrix = [
            (asyncio.TimeoutError(), TardisTimeout),
            (
                asyncssh.Error(code=255, reason="Test", lang="Test"),
                TardisResourceStatusUpdateFailed,
            ),
            (IndexError, TardisResourceStatusUpdateFailed),
            (TardisResourceStatusUpdateFailed, TardisResourceStatusUpdateFailed),
            (
                CommandExecutionFailure(
                    message="Run test command",
                    exit_code=1,
                    stdout="Test",
                    stderr="Test",
                ),
                TardisResourceStatusUpdateFailed,
            ),
            (Exception, TardisError),
        ]

        for to_raise, to_catch in matrix:
            test_exception_handling(to_raise, to_catch)
