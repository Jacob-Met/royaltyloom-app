import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import sandbox_readiness as r


class PrivateConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "paypal-sandbox.env"
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.location = patch.object(r, "_private_file", return_value=self.path)
        self.location.start()
        self.addCleanup(self.location.stop)

    def write(self, body, mode=0o600):
        self.path.write_text(body)
        self.path.chmod(mode)

    def test_literal_file_and_no_environment_mutation(self):
        self.write("# private fixture\nexport PAYPAL_CLIENT_ID='fixture-id'\nPAYPAL_CLIENT_SECRET=\"fixture-secret\" # comment\nPAYPAL_BASE_URL=https://api-m.sandbox.paypal.com\n")
        self.assertEqual(r.credentials(), ("fixture-id", "fixture-secret"))
        request = Mock(return_value={"access_token": "fixture-token"})
        result = r.check_authentication(request)
        self.assertTrue(result["authenticated"])
        self.assertNotIn("fixture-", str(result))
        self.assertEqual(request.call_args.kwargs["basic"], "fixture-id:fixture-secret")
        self.assertNotIn("PAYPAL_CLIENT_ID", os.environ)
        self.assertNotIn("ROYALTY_LOOM_SANDBOX_PAYOUTS", os.environ)

    def test_environment_pair_wins_without_reading_file(self):
        self.write("this is not a valid file")
        with patch.dict(os.environ, {"PAYPAL_CLIENT_ID": "env-id", "PAYPAL_CLIENT_SECRET": "env-secret"}):
            self.assertEqual(r.credentials(), ("env-id", "env-secret"))

    def test_partial_environment_never_mixes_pairs(self):
        self.write("PAYPAL_CLIENT_ID=file-id\nPAYPAL_CLIENT_SECRET=file-secret\n")
        with patch.dict(os.environ, {"PAYPAL_CLIENT_ID": "env-id"}):
            with self.assertRaises(r.SandboxConfigurationError):
                r.credentials()
        with patch.dict(os.environ, {"PAYPAL_CLIENT_ID": "", "PAYPAL_CLIENT_SECRET": ""}):
            self.assertEqual(r.credentials(), ("", ""))

    def test_non_posix_is_environment_only_without_file_access(self):
        with patch.object(r.os, "name", "nt"):
            self.assertEqual(r.credentials(), ("", ""))
            self.assertFalse(r.configuration()["sandbox_credentials_configured"])
            r._private_file.assert_not_called()
            with patch.dict(os.environ, {"PAYPAL_CLIENT_ID":"env-id", "PAYPAL_CLIENT_SECRET":"env-secret"}):
                self.assertEqual(r.credentials(), ("env-id", "env-secret"))
            r._private_file.assert_not_called()

    def test_missing_file(self):
        self.assertEqual(r.credentials(), ("", ""))
        self.assertFalse(r.configuration()["sandbox_credentials_configured"])

    def test_live_endpoint_rejected(self):
        self.write("PAYPAL_CLIENT_ID=id\nPAYPAL_CLIENT_SECRET=secret\nPAYPAL_BASE_URL=https://api-m.paypal.com\n")
        with self.assertRaises(r.SandboxConfigurationError):
            r.credentials()
        with patch.dict(os.environ, {"PAYPAL_CLIENT_ID":"id", "PAYPAL_CLIENT_SECRET":"secret", "PAYPAL_BASE_URL":"https://api-m.paypal.com"}):
            request=Mock()
            self.assertFalse(r.check_authentication(request)["authenticated"])
            request.assert_not_called()

    def test_permissions_and_symlink_rejected(self):
        self.write("PAYPAL_CLIENT_ID=id\nPAYPAL_CLIENT_SECRET=secret", 0o644)
        with self.assertRaises(r.SandboxConfigurationError):
            r.credentials()
        self.path.unlink()
        target = self.path.with_name("target")
        target.write_text("PAYPAL_CLIENT_ID=id\nPAYPAL_CLIENT_SECRET=secret")
        target.chmod(0o600)
        self.path.symlink_to(target)
        with self.assertRaises(r.SandboxConfigurationError):
            r.credentials()

    def test_malformed_and_shell_expressions_fail_closed(self):
        for body in [
            "PAYPAL_CLIENT_ID=$(touch /tmp/must-never-run)",
            "PAYPAL_CLIENT_ID=`echo secret`",
            "PAYPAL_CLIENT_ID='unterminated",
            "PAYPAL_CLIENT_ID=id\nPAYPAL_CLIENT_ID=other",
            "ROYALTY_LOOM_SANDBOX_PAYOUTS=1",
            "PAYPAL_CLIENT_ID=id\nPAYPAL_CLIENT_SECRET=",
            "PAYPAL_CLIENT_ID=id\nPAYPAL_CLIENT_SECRET=secret;echo leak",
            "X=" + "x" * 16385,
        ]:
            with self.subTest(body=body[:20]):
                self.write(body)
                request=Mock()
                result=r.check_authentication(request)
                self.assertFalse(result["authenticated"])
                request.assert_not_called()
                self.assertNotIn("leak", result["message"])
