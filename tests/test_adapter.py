"""Tests for the IProblemReportConfig adapter and its single call point."""

from imio.reportproblem.adapters import ProblemReportConfig
from imio.reportproblem.interfaces import IProblemReportConfig
from imio.reportproblem.interfaces import IReportProblemSettings
from imio.reportproblem.utils import get_report_config
from plone import api
from plone.registry.interfaces import IRegistry
from zope.component import getGlobalSiteManager
from zope.component import getUtility
from zope.interface import alsoProvides
from zope.interface import implementer
from zope.interface import Interface
from zope.interface import noLongerProvides
from zope.interface.verify import verifyObject

import pytest


PREFIX = IReportProblemSettings.__identifier__
RECIPIENTS = f"{PREFIX}.recipients"
PRIVACY_URL = f"{PREFIX}.privacy_url"
PORTAL_EMAIL = "plone.email_from_address"


class IConsumerMarker(Interface):
    """Stands in for the marker interface of a consumer package."""


@implementer(IProblemReportConfig)
class ConsumerReportConfig(ProblemReportConfig):
    """What a consumer package writes: adds its own recipient, keeps the chain."""

    def get_recipients(self):
        return ["consumer@example.org", *super().get_recipients()]


@pytest.fixture
def registry(portal):
    """The site registry, with the add-on settings records guaranteed present.

    The records normally come from the profile; registering the interface here
    keeps these tests independent from what ``registry/main.xml`` ships.
    """
    registry = getUtility(IRegistry)
    if RECIPIENTS not in registry:
        registry.registerInterface(IReportProblemSettings)
    return registry


@pytest.fixture
def content(portal):
    """A plain content object to adapt."""
    with api.env.adopt_roles(["Manager"]):
        return api.content.create(
            container=portal,
            type="Document",
            id="reportable-doc",
            title="A document",
        )


class TestProblemReportConfig:
    def test_interface_is_implemented(self, content):
        """The adapter honours its contract, methods included."""
        assert verifyObject(IProblemReportConfig, ProblemReportConfig(content))

    def test_context_is_stored(self, content):
        assert ProblemReportConfig(content).context is content

    def test_is_enabled_is_true_by_default(self, content):
        """Reporting is offered everywhere unless a consumer says otherwise."""
        assert ProblemReportConfig(content).is_enabled() is True

    def test_get_recipients_reads_the_registry(self, registry, content):
        registry[RECIPIENTS] = ["one@example.org", "two@example.org"]
        assert ProblemReportConfig(content).get_recipients() == [
            "one@example.org",
            "two@example.org",
        ]

    def test_get_recipients_falls_back_on_the_portal_email(self, registry, content):
        registry[RECIPIENTS] = []
        registry[PORTAL_EMAIL] = "portal@example.org"
        assert ProblemReportConfig(content).get_recipients() == ["portal@example.org"]

    def test_get_recipients_is_always_a_list(self, registry, content):
        registry[RECIPIENTS] = []
        registry[PORTAL_EMAIL] = ""
        assert ProblemReportConfig(content).get_recipients() == []

    def test_get_recipients_ignores_blank_entries(self, registry, content):
        registry[RECIPIENTS] = ["  one@example.org  ", "   "]
        assert ProblemReportConfig(content).get_recipients() == ["one@example.org"]

    def test_get_privacy_url_reads_the_registry(self, registry, content):
        registry[PRIVACY_URL] = "https://example.org/privacy"
        assert (
            ProblemReportConfig(content).get_privacy_url()
            == "https://example.org/privacy"
        )

    def test_get_privacy_url_is_none_when_unset(self, registry, content):
        registry[PRIVACY_URL] = None
        assert ProblemReportConfig(content).get_privacy_url() is None

    def test_get_privacy_url_is_none_when_empty(self, registry, content):
        registry[PRIVACY_URL] = "   "
        assert ProblemReportConfig(content).get_privacy_url() is None

    def test_missing_records_do_not_raise(self, portal, content):
        """A profile that has not been applied must not make the add-on explode."""
        registry = getUtility(IRegistry)
        for name in (RECIPIENTS, PRIVACY_URL):
            if name in registry:
                del registry.records[name]
        config = ProblemReportConfig(content)
        assert isinstance(config.get_recipients(), list)
        assert config.get_privacy_url() is None


class TestGetReportConfig:
    def test_returns_the_registered_adapter(self, content):
        config = get_report_config(content)
        assert IProblemReportConfig.providedBy(config)
        assert isinstance(config, ProblemReportConfig)

    def test_default_is_registered_on_star(self, portal):
        """Anything is adaptable, the marker behavior is not required."""
        assert get_report_config(portal) is not None
        assert get_report_config(object()) is not None

    def test_returns_none_when_nothing_is_registered(self, content):
        """The single call point never raises when no adapter is found."""
        gsm = getGlobalSiteManager()
        gsm.unregisterAdapter(
            ProblemReportConfig,
            (Interface,),
            IProblemReportConfig,
        )
        try:
            assert get_report_config(content) is None
        finally:
            gsm.registerAdapter(
                ProblemReportConfig,
                (Interface,),
                IProblemReportConfig,
            )
        assert get_report_config(content) is not None


class TestConsumerOverride:
    """The override story: no overrides.zcml, no adapter conflict."""

    @pytest.fixture
    def consumer(self, content):
        gsm = getGlobalSiteManager()
        gsm.registerAdapter(
            ConsumerReportConfig,
            (IConsumerMarker,),
            IProblemReportConfig,
        )
        alsoProvides(content, IConsumerMarker)
        yield content
        noLongerProvides(content, IConsumerMarker)
        gsm.unregisterAdapter(
            ConsumerReportConfig,
            (IConsumerMarker,),
            IProblemReportConfig,
        )

    def test_more_specific_adapter_wins(self, consumer):
        assert isinstance(get_report_config(consumer), ConsumerReportConfig)

    def test_default_still_wins_elsewhere(self, consumer, portal):
        config = get_report_config(portal)
        assert type(config) is ProblemReportConfig

    def test_super_reaches_the_control_panel(self, registry, consumer):
        registry[RECIPIENTS] = ["controlpanel@example.org"]
        assert get_report_config(consumer).get_recipients() == [
            "consumer@example.org",
            "controlpanel@example.org",
        ]

    def test_super_reaches_the_portal_email_fallback(self, registry, consumer):
        registry[RECIPIENTS] = []
        registry[PORTAL_EMAIL] = "portal@example.org"
        assert get_report_config(consumer).get_recipients() == [
            "consumer@example.org",
            "portal@example.org",
        ]

    def test_inherited_methods_are_kept(self, consumer):
        config = get_report_config(consumer)
        assert verifyObject(IProblemReportConfig, config)
        assert config.is_enabled() is True

    def test_registration_is_cleaned_up(self, content):
        """Runs after the consumer fixture tore its registration down."""
        assert type(get_report_config(content)) is ProblemReportConfig
