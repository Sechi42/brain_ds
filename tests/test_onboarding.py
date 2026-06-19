import io
import unittest
from contextlib import redirect_stdout

from brain_ds.ui.onboarding import Style, banner, branded_print, mascot


class BrandingTests(unittest.TestCase):
    def test_mascot_is_ascii_hippo_with_network_labels(self):
        art = mascot()

        self.assertTrue(art.strip())
        art.encode("ascii")
        self.assertIn("HIPPO", art)
        self.assertIn("ROLES", art)
        self.assertIn("DATA SOURCES", art)
        self.assertIn("o--", art)
        self.assertIn("/____", art)

    def test_mascot_preserves_decision_and_relationship_logo_tokens(self):
        art = mascot()

        art.encode("ascii")
        self.assertIn("DECISIONS", art)
        self.assertIn("BUSINESS RELATIONSHIPS", art)
        self.assertIn("DEPARTMENTS", art)
        self.assertIn("(oo)", art)

    def test_banner_contains_product_name_and_command_context(self):
        text = banner("setup")

        text.encode("ascii")
        self.assertIn("BrainDS", text)
        self.assertIn("setup", text)
        self.assertIn("Enterprise Data & Knowledge Mapper", text)

    def test_branded_print_quiet_suppresses_human_output(self):
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            branded_print("Config target written: .mcp.json", style=Style.SUCCESS, quiet=True)

        self.assertEqual(stdout.getvalue(), "")

    def test_branded_print_keeps_machine_readable_message_intact(self):
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            branded_print("Config target written: .mcp.json", style=Style.SUCCESS)

        self.assertIn("Config target written: .mcp.json", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
