"""Tests for the optional hCaptcha support and for the fail-closed rule.

``plone.formwidget.hcaptcha`` ships in the ``captcha`` extra, so it may or may
not be importable here.  The tests that need the real widget ask for the
``hcaptcha`` fixture and skip cleanly without it; the fail-closed rule, which is
the security relevant branch, is exercised unconditionally by patching the flag
on the module.
"""

from Acquisition import aq_base
from imio.reportproblem import captcha
from imio.reportproblem import report
from imio.reportproblem.browser import form as form_module
from imio.reportproblem.browser.form import ReportProblemForm
from imio.reportproblem.captcha import CAPTCHA_FIELD_NAME
from imio.reportproblem.captcha import get_captcha_fields
from imio.reportproblem.captcha import is_captcha_available
from imio.reportproblem.captcha import verify_captcha
from imio.reportproblem.interfaces import IBrowserLayer
from imio.reportproblem.interfaces import IProblemReportedEvent
from imio.reportproblem.interfaces import IReportProblemSettings
from plone import api
from plone.app.testing import login
from plone.app.testing import logout
from plone.app.testing import TEST_USER_NAME
from plone.app.testing.utils import MockMailHost
from plone.app.z3cform.interfaces import IPloneFormLayer
from plone.dexterity.schema import SCHEMA_CACHE
from plone.protect.authenticator import createToken
from plone.registry.interfaces import IRegistry
from Products.MailHost.interfaces import IMailHost
from zope.component import getGlobalSiteManager
from zope.component import getSiteManager
from zope.component import getUtility
from zope.component import queryMultiAdapter
from zope.interface import alsoProvides

import pytest


PREFIX = IReportProblemSettings.__identifier__
RECIPIENTS = f"{PREFIX}.recipients"

BEHAVIOR_NAME = "imio.reportproblem.reportable"
VIEW_NAME = "report-problem"

SENTINEL_RECIPIENT = "sentinel-recipient@example.invalid"
REASON_TOKEN = "content-error"  # noqa: S105


@pytest.fixture
def hcaptcha():
    """The optional package, or a clean skip when the extra is not installed."""
    return pytest.importorskip("plone.formwidget.hcaptcha")


@pytest.fixture
def registry(portal):
    registry = getUtility(IRegistry)
    if RECIPIENTS not in registry:
        registry.registerInterface(IReportProblemSettings)
    registry[RECIPIENTS] = [SENTINEL_RECIPIENT]
    registry["plone.email_from_address"] = "site@example.invalid"
    registry["plone.smtp_host"] = "localhost"
    return registry


@pytest.fixture
def request_with_layers(http_request):
    alsoProvides(http_request, IBrowserLayer)
    alsoProvides(http_request, IPloneFormLayer)
    return http_request


@pytest.fixture
def reportable(portal, get_fti):
    fti = get_fti("Document")
    original = tuple(fti.behaviors)
    fti.behaviors = (*original, BEHAVIOR_NAME)
    SCHEMA_CACHE.invalidate(fti)
    yield fti
    fti.behaviors = original
    SCHEMA_CACHE.invalidate(fti)


@pytest.fixture
def document(portal, reportable, registry):
    with api.env.adopt_roles(["Manager"]):
        return api.content.create(
            container=portal,
            type="Document",
            id="captcha-document",
            title="A reportable document",
        )


@pytest.fixture
def anonymous(portal):
    """Run the test as an anonymous visitor."""
    logout()
    yield
    login(portal, TEST_USER_NAME)


@pytest.fixture
def with_captcha(monkeypatch):
    """Pretend the extra is installed, without needing the real widget."""
    monkeypatch.setattr(captcha, "HAS_CAPTCHA", True)


@pytest.fixture
def without_captcha(monkeypatch):
    """Pretend the extra is not installed, whatever this install has."""
    monkeypatch.setattr(captcha, "HAS_CAPTCHA", False)


@pytest.fixture
def mailhost(portal, registry):
    """Collect the messages instead of sending them."""
    original = portal.MailHost
    mock = MockMailHost("MailHost")
    portal.MailHost = mock
    site_manager = getSiteManager(context=portal)
    site_manager.unregisterUtility(provided=IMailHost)
    site_manager.registerUtility(mock, provided=IMailHost)
    yield mock
    portal.MailHost = original
    site_manager.unregisterUtility(provided=IMailHost)
    site_manager.registerUtility(aq_base(original), provided=IMailHost)


@pytest.fixture
def received():
    events = []

    def handler(event):
        events.append(event)

    site_manager = getGlobalSiteManager()
    site_manager.registerHandler(handler, (IProblemReportedEvent,))
    yield events
    site_manager.unregisterHandler(handler, (IProblemReportedEvent,))


def get_form(context, request):
    return queryMultiAdapter((context, request), name=VIEW_NAME)


class TestAvailabilityFlag:
    def test_flag_is_a_boolean(self):
        assert isinstance(captcha.HAS_CAPTCHA, bool)

    def test_helper_reflects_the_flag(self):
        assert is_captcha_available() is captcha.HAS_CAPTCHA

    def test_helper_reads_the_flag_at_call_time(self, without_captcha):
        """Which is what lets a test exercise both branches on one install."""
        assert is_captcha_available() is False


class TestFailClosed:
    """The security relevant branch: it is tested whatever this install has."""

    def test_anonymous_is_refused_without_a_captcha(
        self, document, anonymous, without_captcha
    ):
        assert report.is_report_available(document) is False

    def test_anonymous_is_offered_the_form_with_a_captcha(
        self, document, anonymous, with_captcha
    ):
        assert report.is_report_available(document) is True

    def test_authenticated_is_offered_the_form_without_a_captcha(
        self, document, without_captcha
    ):
        """An account is already accountable, so nothing changes for it."""
        assert report.is_report_available(document) is True

    def test_a_missing_recipient_is_the_same_condition(
        self, registry, document, with_captcha, anonymous
    ):
        registry[RECIPIENTS] = []
        registry["plone.email_from_address"] = ""

        assert report.is_report_available(document) is False

    def test_the_form_is_not_offered_to_an_anonymous_visitor(
        self, document, request_with_layers, anonymous, without_captcha
    ):
        view = get_form(document, request_with_layers)
        view.update()

        assert view.available is False
        assert view.widgets is None

    def test_no_captcha_field_is_added_when_the_extra_is_missing(
        self, document, request_with_layers, without_captcha
    ):
        view = get_form(document, request_with_layers)
        view.update()

        assert CAPTCHA_FIELD_NAME not in view.widgets

    def test_get_captcha_fields_is_none_without_the_extra(self, without_captcha):
        assert get_captcha_fields() is None

    def test_verify_is_false_without_the_extra(
        self, portal, request_with_layers, without_captcha
    ):
        assert verify_captcha(portal, request_with_layers) is False

    def test_verify_is_false_when_the_view_is_not_registered(
        self, portal, request_with_layers, with_captcha
    ):
        """Fail closed: a captcha that cannot be verified rejects the report."""
        assert queryMultiAdapter((portal, request_with_layers), name="hcaptcha") is None
        assert verify_captcha(portal, request_with_layers) is False


class TestShowCaptcha:
    def test_authenticated_never_gets_one(self, document, request_with_layers):
        view = get_form(document, request_with_layers)

        assert view.show_captcha() is False

    def test_authenticated_never_gets_one_even_with_the_extra(
        self, document, request_with_layers, with_captcha
    ):
        view = get_form(document, request_with_layers)

        assert view.show_captcha() is False

    def test_anonymous_gets_one_when_the_extra_is_there(
        self, document, request_with_layers, anonymous, with_captcha
    ):
        view = get_form(document, request_with_layers)

        assert view.show_captcha() is True

    def test_anonymous_gets_none_without_the_extra(
        self, document, request_with_layers, anonymous, without_captcha
    ):
        view = get_form(document, request_with_layers)

        assert view.show_captcha() is False


class TestHandlerRejectsABadCaptcha:
    """Validated in the handler, as the widget ships no registered validator."""

    def test_a_failing_captcha_stops_the_report(
        self, monkeypatch, document, request_with_layers, mailhost, received
    ):
        monkeypatch.setattr(ReportProblemForm, "show_captcha", lambda self: True)
        monkeypatch.setattr(
            form_module, "verify_captcha", lambda context, request: False
        )
        view = get_form(document, request_with_layers)
        request_with_layers.form.clear()
        request_with_layers.form.update({
            "form.widgets.name": "Sentinel Reporter",
            "form.widgets.email": "sentinel.reporter@example.invalid",
            "form.widgets.reason": [REASON_TOKEN],
            "form.widgets.message": "Something is wrong here.",
            "form.buttons.send": "Send the report",
            "_authenticator": createToken(),
        })
        request_with_layers.REQUEST_METHOD = "POST"

        view.update()

        assert received == []
        assert list(mailhost.messages) == []
        assert view.status == form_module.CAPTCHA_ERROR

    def test_a_passing_captcha_lets_the_report_through(
        self, monkeypatch, document, request_with_layers, mailhost, received
    ):
        monkeypatch.setattr(ReportProblemForm, "show_captcha", lambda self: True)
        monkeypatch.setattr(
            form_module, "verify_captcha", lambda context, request: True
        )
        view = get_form(document, request_with_layers)
        request_with_layers.form.clear()
        request_with_layers.form.update({
            "form.widgets.name": "Sentinel Reporter",
            "form.widgets.email": "sentinel.reporter@example.invalid",
            "form.widgets.reason": [REASON_TOKEN],
            "form.widgets.message": "Something is wrong here.",
            "form.buttons.send": "Send the report",
            "_authenticator": createToken(),
        })
        request_with_layers.REQUEST_METHOD = "POST"

        view.update()

        assert len(received) == 1
        assert len(mailhost.messages) == 1


class TestWithTheExtraInstalled:
    """Only run when ``imio.reportproblem[captcha]`` is actually installed."""

    def test_the_widget_is_importable_from_the_package_root(self, hcaptcha):
        """The import point the module uses, stable across 1.x and 3.x."""
        assert hcaptcha.HCaptchaFieldWidget is not None

    def test_the_flag_is_true(self, hcaptcha):
        assert captcha.HAS_CAPTCHA is True

    def test_the_schema_carries_the_field(self, hcaptcha):
        assert captcha.ICaptchaSchema is not None
        assert CAPTCHA_FIELD_NAME in captcha.ICaptchaSchema.names()

    def test_the_field_is_not_required(self, hcaptcha):
        """The handler validates it; a required field would error out first."""
        assert captcha.ICaptchaSchema[CAPTCHA_FIELD_NAME].required is False

    def test_the_fields_use_the_hcaptcha_widget(self, hcaptcha):
        fields = get_captcha_fields()

        assert fields is not None
        assert (
            fields[CAPTCHA_FIELD_NAME].widgetFactory.default
            is hcaptcha.HCaptchaFieldWidget
        )

    def test_an_anonymous_form_adds_the_field(
        self, hcaptcha, document, request_with_layers, anonymous
    ):
        view = get_form(document, request_with_layers)
        view.updateFields()

        assert CAPTCHA_FIELD_NAME in view.fields

    def test_an_authenticated_form_does_not(
        self, hcaptcha, document, request_with_layers
    ):
        view = get_form(document, request_with_layers)
        view.updateFields()

        assert CAPTCHA_FIELD_NAME not in view.fields
