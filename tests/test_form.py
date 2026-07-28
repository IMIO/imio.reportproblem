"""Tests for the @@report-problem form, its two display modes included."""

from Acquisition import aq_base
from email import message_from_bytes
from imio.reportproblem import captcha
from imio.reportproblem.browser.form import IReportProblemForm
from imio.reportproblem.browser.form import ReportProblemForm
from imio.reportproblem.browser.form import UNAVAILABLE
from imio.reportproblem.constants import DEFAULT_CONFIRMATION_MESSAGE
from imio.reportproblem.constants import DEFAULT_FORM_INTRO
from imio.reportproblem.constants import DEFAULT_FORM_TITLE
from imio.reportproblem.constants import FORM_CONTENT_ID
from imio.reportproblem.interfaces import IBrowserLayer
from imio.reportproblem.interfaces import IProblemReportedEvent
from imio.reportproblem.interfaces import IReportProblemSettings
from imio.reportproblem.report import translate
from lxml import html
from plone import api
from plone.app.testing import login
from plone.app.testing import logout
from plone.app.testing import setRoles
from plone.app.testing import TEST_USER_ID
from plone.app.testing import TEST_USER_NAME
from plone.app.testing.utils import MockMailHost
from plone.app.z3cform.interfaces import IPloneFormLayer
from plone.dexterity.schema import SCHEMA_CACHE
from plone.protect.authenticator import createToken
from plone.registry.interfaces import IRegistry
from Products.MailHost.interfaces import IMailHost
from Products.statusmessages.interfaces import IStatusMessage
from zExceptions import Forbidden
from zope.component import getGlobalSiteManager
from zope.component import getSiteManager
from zope.component import getUtility
from zope.component import queryMultiAdapter
from zope.interface import alsoProvides

import pytest


PREFIX = IReportProblemSettings.__identifier__
RECIPIENTS = f"{PREFIX}.recipients"
FORM_TITLE = f"{PREFIX}.form_title"
FORM_INTRO = f"{PREFIX}.form_intro"
CONFIRMATION = f"{PREFIX}.confirmation_message"

BEHAVIOR_NAME = "imio.reportproblem.reportable"
VIEW_NAME = "report-problem"

SENTINEL_RECIPIENT = "sentinel-recipient@example.invalid"
SENTINEL_FULLNAME = "Sentinel Fullname"
SENTINEL_MEMBER_EMAIL = "sentinel.member@example.invalid"
SENTINEL_MESSAGE = "The annex is unreadable, it opens on a blank page."

REASON_TOKEN = "content-error"  # noqa: S105


@pytest.fixture
def registry(portal):
    """The site registry, with the add-on records guaranteed present."""
    registry = getUtility(IRegistry)
    if RECIPIENTS not in registry:
        registry.registerInterface(IReportProblemSettings)
    registry["plone.email_from_address"] = "site@example.invalid"
    registry["plone.email_from_name"] = "Sentinel site"
    registry["plone.smtp_host"] = "localhost"
    return registry


@pytest.fixture
def recipients(registry):
    registry[RECIPIENTS] = [SENTINEL_RECIPIENT]
    return [SENTINEL_RECIPIENT]


@pytest.fixture
def request_with_layers(http_request):
    """The integration request, marked as a traversal would mark it.

    ``IBrowserLayer`` is the add-on's own layer, applied at traversal time by
    ``plone.browserlayer``; ``IPloneFormLayer`` is what the z3c.form widgets and
    the ``ploneform-macros`` view are registered for.
    """
    alsoProvides(http_request, IBrowserLayer)
    alsoProvides(http_request, IPloneFormLayer)
    return http_request


@pytest.fixture
def reportable(portal, get_fti):
    """Enable the behavior on ``Document`` for the duration of the test."""
    fti = get_fti("Document")
    original = tuple(fti.behaviors)
    fti.behaviors = (*original, BEHAVIOR_NAME)
    SCHEMA_CACHE.invalidate(fti)
    yield fti
    fti.behaviors = original
    SCHEMA_CACHE.invalidate(fti)


@pytest.fixture
def document(portal, reportable):
    """A document carrying the marker behavior."""
    with api.env.adopt_roles(["Manager"]):
        return api.content.create(
            container=portal,
            type="Document",
            id="reportable-document",
            title="A reportable document",
        )


@pytest.fixture
def plain_document(portal):
    """A document *without* the behavior: no form must be registered for it."""
    with api.env.adopt_roles(["Manager"]):
        return api.content.create(
            container=portal,
            type="Document",
            id="plain-document",
            title="A plain document",
        )


@pytest.fixture
def member(portal):
    """The test user, with the member properties the form pre-fills from."""
    setRoles(portal, TEST_USER_ID, ["Manager"])
    member = api.user.get_current()
    member.setMemberProperties(
        mapping={"fullname": SENTINEL_FULLNAME, "email": SENTINEL_MEMBER_EMAIL}
    )
    return member


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
    """Collect every IProblemReportedEvent fired while the test runs."""
    events = []

    def handler(event):
        events.append(event)

    site_manager = getGlobalSiteManager()
    site_manager.registerHandler(handler, (IProblemReportedEvent,))
    yield events
    site_manager.unregisterHandler(handler, (IProblemReportedEvent,))


@pytest.fixture
def no_captcha(monkeypatch):
    """Pretend the ``captcha`` extra is not installed.

    Patched on the module rather than read off the environment, so the
    fail-closed branch is exercised whether or not the extra happens to be
    available here.
    """
    monkeypatch.setattr(captcha, "HAS_CAPTCHA", False)


def get_form(context, request):
    """Return the ``@@report-problem`` view, or None when not registered."""
    return queryMultiAdapter((context, request), name=VIEW_NAME)


def submission(request, **overrides):
    """Fill ``request.form`` as a submitted report, token included."""
    data = {
        "form.widgets.name": "Sentinel Reporter",
        "form.widgets.email": "sentinel.reporter@example.invalid",
        "form.widgets.reason": [REASON_TOKEN],
        "form.widgets.message": SENTINEL_MESSAGE,
        "form.buttons.send": "Send the report",
        "_authenticator": createToken(),
    }
    data.update(overrides)
    request.form.clear()
    request.form.update(data)
    request.REQUEST_METHOD = "POST"
    return request


class TestRegistration:
    def test_registered_for_the_marker_behavior(self, document, request_with_layers):
        assert get_form(document, request_with_layers) is not None

    def test_is_the_form_class(self, document, request_with_layers):
        assert isinstance(get_form(document, request_with_layers), ReportProblemForm)

    def test_not_registered_without_the_behavior(
        self, plain_document, request_with_layers
    ):
        """No behavior, no view: the button cannot lead anywhere either."""
        assert get_form(plain_document, request_with_layers) is None

    def test_schema_holds_the_four_reporter_fields(self):
        assert list(IReportProblemForm.names()) == [
            "name",
            "email",
            "reason",
            "message",
        ]

    def test_reason_uses_the_named_vocabulary(self):
        assert (
            IReportProblemForm["reason"].vocabularyName == "imio.reportproblem.reasons"
        )

    def test_context_is_ignored(self, document, request_with_layers):
        """A report is transient: nothing is read from nor written to the content."""
        assert get_form(document, request_with_layers).ignoreContext is True

    def test_csrf_protection_is_enabled(self, document, request_with_layers):
        assert get_form(document, request_with_layers).enableCSRFProtection is True


class TestFailClosed:
    """No captcha for an anonymous visitor means no form at all."""

    def test_anonymous_without_captcha_is_not_offered_the_form(
        self, portal, recipients, document, request_with_layers, no_captcha
    ):
        logout()
        try:
            view = get_form(document, request_with_layers)
            view.update()

            assert view.available is False
            assert view.widgets is None
        finally:
            login(portal, TEST_USER_NAME)

    def test_anonymous_without_captcha_gets_no_fields_rendered(
        self, portal, recipients, document, request_with_layers, no_captcha
    ):
        with api.env.adopt_roles(["Manager"]):
            api.content.transition(obj=document, transition="publish")
        logout()
        try:
            rendered = get_form(document, request_with_layers)()
        finally:
            login(portal, TEST_USER_NAME)

        assert "form.widgets.email" not in rendered
        assert "form.buttons.send" not in rendered

    def test_authenticated_is_unaffected_by_the_missing_captcha(
        self, recipients, document, request_with_layers, no_captcha
    ):
        view = get_form(document, request_with_layers)
        view.update()

        assert view.available is True
        assert view.show_captcha() is False

    def test_no_recipient_is_the_same_condition(
        self, registry, document, request_with_layers
    ):
        registry[RECIPIENTS] = []
        registry["plone.email_from_address"] = ""

        view = get_form(document, request_with_layers)
        view.update()

        assert view.available is False
        assert view.widgets is None

    def test_unavailable_form_renders_an_explanation(
        self, registry, document, request_with_layers
    ):
        registry[RECIPIENTS] = []
        registry["plone.email_from_address"] = ""

        rendered = get_form(document, request_with_layers)()

        assert "form.buttons.send" not in rendered
        assert translate(UNAVAILABLE) in rendered


class TestAuthenticatedReporter:
    def test_name_is_prefilled_from_fullname(
        self, member, recipients, document, request_with_layers
    ):
        view = get_form(document, request_with_layers)
        view.update()

        assert view.widgets["name"].value == SENTINEL_FULLNAME

    def test_email_is_prefilled_from_the_member_email(
        self, member, recipients, document, request_with_layers
    ):
        view = get_form(document, request_with_layers)
        view.update()

        assert view.widgets["email"].value == SENTINEL_MEMBER_EMAIL

    def test_prefilled_fields_stay_editable(
        self, member, recipients, document, request_with_layers
    ):
        view = get_form(document, request_with_layers)
        view.update()

        assert view.widgets["name"].mode == "input"
        assert view.widgets["email"].mode == "input"

    def test_a_submitted_value_wins_over_the_prefill(
        self, member, recipients, document, request_with_layers
    ):
        """A manager reporting from another address only has to type over it."""
        request_with_layers.form.clear()
        request_with_layers.form["form.widgets.name"] = "Someone Else"
        # CMFPlone refuses to pre-fill a widget from a request whose method is
        # not the form's own, so a submitted value only counts on a POST.
        request_with_layers.REQUEST_METHOD = "POST"

        view = get_form(document, request_with_layers)
        view.update()

        assert view.widgets["name"].value == "Someone Else"

    def test_no_captcha_field_is_added(
        self, member, recipients, document, request_with_layers
    ):
        """An account is already accountable, its userid travels with the report."""
        view = get_form(document, request_with_layers)
        view.update()

        assert "captcha" not in view.widgets

    def test_anonymous_gets_no_prefill(
        self, portal, recipients, document, request_with_layers
    ):
        logout()
        try:
            assert get_form(document, request_with_layers).get_member_defaults() == {}
        finally:
            login(portal, TEST_USER_NAME)


class TestWording:
    def test_title_and_intro_fall_back_on_the_translated_defaults(
        self, registry, document, request_with_layers
    ):
        registry[FORM_TITLE] = ""
        registry[FORM_INTRO] = ""

        view = get_form(document, request_with_layers)

        assert view.label == DEFAULT_FORM_TITLE
        assert view.description == DEFAULT_FORM_INTRO

    def test_title_and_intro_come_from_the_records(
        self, registry, document, request_with_layers
    ):
        registry[FORM_TITLE] = "Sentinel form title"
        registry[FORM_INTRO] = "Sentinel form intro"

        view = get_form(document, request_with_layers)

        assert view.label == "Sentinel form title"
        assert view.description == "Sentinel form intro"


class TestDisplayModes:
    """One view, two modes: what makes it work is where the markup sits."""

    @pytest.fixture
    def rendered(self, registry, recipients, document, request_with_layers):
        registry[FORM_TITLE] = "Sentinel form title"
        registry[FORM_INTRO] = "Sentinel form intro"
        return html.fromstring(get_form(document, request_with_layers)())

    @pytest.fixture
    def extracted(self, rendered):
        """What the modal keeps: the element ``FORM_CONTENT_ID`` names."""
        return rendered.get_element_by_id(FORM_CONTENT_ID)

    def test_the_extracted_element_exists(self, extracted):
        assert extracted is not None

    def test_title_is_inside_the_extracted_element(self, extracted):
        assert "Sentinel form title" in extracted.text_content()

    def test_intro_is_inside_the_extracted_element(self, extracted):
        assert "Sentinel form intro" in extracted.text_content()

    def test_form_is_inside_the_extracted_element(self, extracted):
        assert extracted.xpath(".//form")
        assert extracted.xpath('.//*[@name="form.widgets.message"]')
        assert extracted.xpath('.//*[@name="form.buttons.send"]')

    def test_protect_token_is_inside_the_extracted_element(self, extracted):
        """So the token travels with an AJAX submission too."""
        tokens = extracted.xpath('.//input[@name="_authenticator"]')

        assert len(tokens) == 1
        assert tokens[0].get("value")

    def test_back_link_is_outside_the_extracted_element(self, rendered, extracted):
        """The modal does not pick it up; the standalone page shows it."""
        assert rendered.xpath('//a[contains(@class, "report-problem-back-link")]')
        assert not extracted.xpath('.//a[contains(@class, "report-problem-back-link")]')

    def test_back_link_points_at_the_content(self, rendered, document):
        links = rendered.xpath('//a[contains(@class, "report-problem-back-link")]')

        assert links[0].get("href") == document.absolute_url()

    def test_no_captcha_script_without_the_captcha(
        self, registry, recipients, document, request_with_layers, no_captcha
    ):
        assert "hcaptcha" not in get_form(document, request_with_layers)()


class TestSubmission:
    def test_a_valid_submission_sends_the_report(
        self, member, recipients, mailhost, received, document, request_with_layers
    ):
        view = get_form(document, request_with_layers)
        submission(request_with_layers)

        view.update()

        assert len(mailhost.messages) == 1
        assert len(received) == 1

    def test_the_payload_carries_the_submitted_values(
        self, member, recipients, mailhost, received, document, request_with_layers
    ):
        view = get_form(document, request_with_layers)
        submission(request_with_layers)

        view.update()

        data = received[0].data
        assert data["reason"] == REASON_TOKEN
        assert data["message"] == SENTINEL_MESSAGE
        assert data["userid"] == TEST_USER_ID
        assert data["review_state"] == api.content.get_state(document)

    def test_the_mail_reaches_the_configured_recipient(
        self, member, recipients, mailhost, document, request_with_layers
    ):
        view = get_form(document, request_with_layers)
        submission(request_with_layers)

        view.update()

        message = message_from_bytes(mailhost.messages[0])
        assert SENTINEL_RECIPIENT in message["To"]

    def test_a_successful_send_redirects_to_the_content(
        self, member, recipients, mailhost, document, request_with_layers
    ):
        """So the confirmation shows there, not inside the modal."""
        view = get_form(document, request_with_layers)
        submission(request_with_layers)

        view.update()

        assert request_with_layers.response.getStatus() == 302
        assert request_with_layers.response.getHeader("Location") == (
            document.absolute_url()
        )

    def test_a_successful_send_adds_the_confirmation_message(
        self, member, recipients, mailhost, document, request_with_layers
    ):
        view = get_form(document, request_with_layers)
        submission(request_with_layers)

        view.update()

        messages = IStatusMessage(request_with_layers).show()
        assert [message.message for message in messages] == [
            translate(DEFAULT_CONFIRMATION_MESSAGE)
        ]

    def test_the_confirmation_message_comes_from_the_record(
        self,
        registry,
        member,
        recipients,
        mailhost,
        document,
        request_with_layers,
    ):
        registry[CONFIRMATION] = "Sentinel confirmation"
        view = get_form(document, request_with_layers)
        submission(request_with_layers)

        view.update()

        messages = IStatusMessage(request_with_layers).show()
        assert [message.message for message in messages] == ["Sentinel confirmation"]

    def test_a_missing_field_is_refused(
        self, member, recipients, mailhost, received, document, request_with_layers
    ):
        view = get_form(document, request_with_layers)
        submission(request_with_layers, **{"form.widgets.message": ""})

        view.update()

        assert view.widgets.errors
        assert list(mailhost.messages) == []
        assert received == []

    def test_an_invalid_email_is_refused(
        self, member, recipients, mailhost, received, document, request_with_layers
    ):
        view = get_form(document, request_with_layers)
        submission(request_with_layers, **{"form.widgets.email": "not-an-address"})

        view.update()

        assert view.widgets.errors
        assert list(mailhost.messages) == []
        assert received == []

    def test_a_submission_without_the_protect_token_is_refused(
        self, member, recipients, mailhost, received, document, request_with_layers
    ):
        view = get_form(document, request_with_layers)
        submission(request_with_layers, _authenticator="")

        with pytest.raises(Forbidden):
            view.update()

        assert list(mailhost.messages) == []
        assert received == []
