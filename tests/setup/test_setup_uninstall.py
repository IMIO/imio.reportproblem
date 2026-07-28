from imio.reportproblem import PACKAGE_NAME

import pytest


class TestSetupUninstall:
    @pytest.fixture(autouse=True)
    def uninstalled(self, installer):
        installer.uninstall_product(PACKAGE_NAME)

    def test_addon_uninstalled(self, installer):
        """Test if imio.reportproblem is uninstalled."""
        assert installer.is_product_installed(PACKAGE_NAME) is False

    def test_browserlayer_not_registered(self, browser_layers):
        """Test that IBrowserLayer is not registered."""
        from imio.reportproblem.interfaces import IBrowserLayer

        assert IBrowserLayer not in browser_layers

    def test_controlpanel_configlet_removed(self, portal):
        """The configlet must go, or Site Setup keeps a dead entry.

        Its view is registered on the browser layer, which uninstalling
        removes, so a leftover configlet would raise on click.
        """
        controlpanel = portal["portal_controlpanel"]
        action_ids = [action.getId() for action in controlpanel.listActions()]

        assert "imio.reportproblem.settings" not in action_ids
