from tardis.rest.hash_credentials.hash_credentials import hash_credentials

from typer.testing import CliRunner
from typer import Typer
from unittest import TestCase


class TestHashCredentials(TestCase):
    def setUp(self) -> None:
        self.app = Typer()
        self.app.command()(hash_credentials)

        self.runner = CliRunner()

    def test_hash_credentials(self):
        result = self.runner.invoke(self.app)
        self.assertNotEqual(result.exit_code, 0)
        try:
            output = result.stderr
        except ValueError:
            output = result.stdout
        self.assertIn("Missing argument", output)
        self.assertIn("password", output.lower())

        result = self.runner.invoke(self.app, "test_password")
        self.assertEqual(result.exit_code, 0)
        # Hash is salted, therefore exact comparison is not possible
        self.assertTrue("$2b$12$" in result.stdout)
        self.assertEqual(60, len(result.stdout.strip()))
