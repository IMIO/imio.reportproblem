"""Tests for the ``imio.reportproblem.settings`` helpers."""

from imio.reportproblem import settings
from imio.reportproblem.constants import DEFAULT_BUTTON_LABEL
from imio.reportproblem.constants import DEFAULT_CONFIRMATION_MESSAGE
from imio.reportproblem.constants import DEFAULT_FORM_INTRO
from imio.reportproblem.constants import DEFAULT_FORM_TITLE
from imio.reportproblem.constants import DEFAULT_REASONS
from imio.reportproblem.constants import DISPLAY_MODE_MODAL
from imio.reportproblem.constants import DISPLAY_MODE_PAGE
from imio.reportproblem.settings import get_display_mode
from imio.reportproblem.settings import get_setting
from imio.reportproblem.settings import get_wording
from imio.reportproblem.settings import RECORD_PREFIX
from plone import api
from zope.i18nmessageid import Message

import pytest


WORDING_FALLBACKS = (
    ("button_label", DEFAULT_BUTTON_LABEL),
    ("form_title", DEFAULT_FORM_TITLE),
    ("form_intro", DEFAULT_FORM_INTRO),
    ("confirmation_message", DEFAULT_CONFIRMATION_MESSAGE),
)


class TestGetSetting:
    def test_returns_the_record_value(self, portal):
        assert get_setting("reasons") == list(DEFAULT_REASONS)

    def test_unknown_name_does_not_raise(self, portal):
        assert get_setting("no_such_record") is None

    def test_unknown_name_returns_the_given_default(self, portal):
        assert get_setting("no_such_record", "fallback") == "fallback"


class TestGetWording:
    @pytest.mark.parametrize(("name", "fallback"), WORDING_FALLBACKS)
    def test_empty_record_returns_the_fallback_message(self, portal, name, fallback):
        result = get_wording(name, fallback)

        assert result is fallback
        assert isinstance(result, Message)
        assert result.domain == "imio.reportproblem"

    @pytest.mark.parametrize(("name", "fallback"), WORDING_FALLBACKS)
    def test_configured_value_is_used_as_is(self, portal, name, fallback):
        api.portal.set_registry_record(f"{RECORD_PREFIX}.{name}", "A hand typed label")

        assert get_wording(name, fallback) == "A hand typed label"

    def test_value_is_stripped(self, portal):
        api.portal.set_registry_record(f"{RECORD_PREFIX}.button_label", "  Report it  ")

        assert get_wording("button_label", DEFAULT_BUTTON_LABEL) == "Report it"

    def test_whitespace_only_value_falls_back(self, portal):
        api.portal.set_registry_record(f"{RECORD_PREFIX}.button_label", "   ")

        assert get_wording("button_label", DEFAULT_BUTTON_LABEL) is DEFAULT_BUTTON_LABEL


class TestGetDisplayMode:
    def test_defaults_to_modal(self, portal):
        assert get_display_mode() == DISPLAY_MODE_MODAL

    def test_follows_the_registry(self, portal):
        api.portal.set_registry_record(
            f"{RECORD_PREFIX}.form_display_mode", DISPLAY_MODE_PAGE
        )

        assert get_display_mode() == DISPLAY_MODE_PAGE


class TestWithoutRegistry:
    """The helpers must survive being called before the profile is applied."""

    @pytest.fixture(autouse=True)
    def _no_registry(self, monkeypatch):
        monkeypatch.setattr(settings, "queryUtility", lambda _iface: None)

    def test_get_setting_returns_the_default(self):
        assert get_setting("reasons") is None
        assert get_setting("reasons", []) == []

    def test_get_wording_returns_the_fallback(self):
        assert get_wording("form_title", DEFAULT_FORM_TITLE) is DEFAULT_FORM_TITLE

    def test_get_display_mode_returns_modal(self):
        assert get_display_mode() == DISPLAY_MODE_MODAL
