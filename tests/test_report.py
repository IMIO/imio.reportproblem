"""Tests for the sending logic extracted out of the form handler."""

from Acquisition import aq_base
from email import message_from_bytes
from email import message_from_string
from email.header import decode_header
from imio.reportproblem import report
from imio.reportproblem.constants import DEFAULT_SUBJECT_TEMPLATE
from imio.reportproblem.interfaces import IProblemReportedEvent
from imio.reportproblem.interfaces import IReportProblemSettings
from imio.reportproblem.report import send_problem_report
from plone import api
from plone.app.testing import login
from plone.app.testing import logout
from plone.app.testing import SITE_OWNER_NAME
from plone.app.testing import TEST_USER_NAME
from plone.app.testing.utils import MockMailHost
from plone.registry.interfaces import IRegistry
from Products.MailHost.interfaces import IMailHost
from zope.component import getGlobalSiteManager
from zope.component import getSiteManager
from zope.component import getUtility

import pytest


PREFIX = IReportProblemSettings.__identifier__
RECIPIENTS = f"{PREFIX}.recipients"
SUBJECT_TEMPLATE = f"{PREFIX}.subject_template"

#: Distinctive values, so an assertion on the composed body cannot pass by
#: accident on a string Plone happens to put there anyway.
SENTINEL_TITLE = "Zorglub sentinel document"
SENTINEL_NAME = "Sentinel Reporter"
SENTINEL_EMAIL = "sentinel.reporter@example.invalid"
SENTINEL_MESSAGE = "The third paragraph mentions a frobnicated deadline."
SENTINEL_RECIPIENT = "sentinel-recipient@example.invalid"

#: The form hands over the reason *token*, never its translated title.  Not a
#: credential, whatever ``flake8-bandit`` makes of the name.
REASON_TOKEN = "content-error"  # noqa: S105
REASON_TITLE = "Content error"

#: What the reporter submits, and nothing more: every technical field of the
#: report is derived server side.
SUBMITTED = {
    "name": SENTINEL_NAME,
    "email": SENTINEL_EMAIL,
    "reason": REASON_TOKEN,
    "message": SENTINEL_MESSAGE,
}


@pytest.fixture
def registry(portal):
    """The site registry, with the add-on records guaranteed present."""
    registry = getUtility(IRegistry)
    if RECIPIENTS not in registry:
        registry.registerInterface(IReportProblemSettings)
    return registry


@pytest.fixture
def document(portal):
    """A published document to report a problem on."""
    with api.env.adopt_roles(["Manager"]):
        doc = api.content.create(
            container=portal,
            type="Document",
            id="sentinel-document",
            title=SENTINEL_TITLE,
        )
        api.content.transition(obj=doc, transition="publish")
    return doc


@pytest.fixture
def recipients(registry):
    """A single, recognisable recipient configured site wide."""
    registry[RECIPIENTS] = [SENTINEL_RECIPIENT]
    return [SENTINEL_RECIPIENT]


@pytest.fixture
def mailhost(portal, registry):
    """Collect the messages instead of sending them.

    Mirrors ``plone.app.testing``'s MOCK_MAILHOST_FIXTURE, set up here rather
    than in a layer so the whole suite keeps running on the integration layer.
    """
    registry["plone.email_from_address"] = "site@example.invalid"
    registry["plone.email_from_name"] = "Sentinel site"
    registry["plone.smtp_host"] = "localhost"
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
def without_workflow(portal):
    """Take the workflow away from ``Document``, as some content types have."""
    workflow_tool = api.portal.get_tool("portal_workflow")
    original = workflow_tool.getChainForPortalType("Document")
    workflow_tool.setChainForPortalTypes(("Document",), ())
    yield
    workflow_tool.setChainForPortalTypes(("Document",), original or ())


def sent_message(mailhost):
    """Return the single message the mock mail host collected, parsed."""
    assert len(mailhost.messages) == 1
    raw = mailhost.messages[0]
    if isinstance(raw, bytes):
        return message_from_bytes(raw)
    if isinstance(raw, str):
        return message_from_string(raw)
    return raw


def header(message, name):
    """Return a decoded header of a collected message."""
    parts = decode_header(message[name])
    return "".join(
        part.decode(charset or "utf-8") if isinstance(part, bytes) else part
        for part, charset in parts
    )


def body_of(message):
    """Return the decoded text body of a collected message."""
    payload = message.get_payload(decode=True)
    return payload.decode(message.get_content_charset() or "utf-8")


class TestBuildPayload:
    """The payload keys are a cross-package contract, see subscribers.audit."""

    def test_keys_are_exactly_the_contract(self, document):
        payload = report.build_payload(document, SUBMITTED)

        assert set(payload) == {
            "reason",
            "review_state",
            "userid",
            "name",
            "email",
            "message",
        }

    def test_reason_is_the_token(self, document):
        assert report.build_payload(document, SUBMITTED)["reason"] == REASON_TOKEN

    def test_review_state_is_the_publication_state(self, document):
        payload = report.build_payload(document, SUBMITTED)

        assert payload["review_state"] == "published"
        assert payload["review_state"] == api.content.get_state(document)

    def test_review_state_is_none_without_workflow(self, document, without_workflow):
        assert report.build_payload(document, SUBMITTED)["review_state"] is None

    def test_userid_is_the_current_user(self, document):
        payload = report.build_payload(document, SUBMITTED)

        assert payload["userid"] == api.user.get_current().getId()

    def test_userid_is_none_for_anonymous(self, portal, document):
        logout()

        assert report.build_payload(document, SUBMITTED)["userid"] is None

    def test_reporter_fields_are_carried_over(self, document):
        payload = report.build_payload(document, SUBMITTED)

        assert payload["name"] == SENTINEL_NAME
        assert payload["email"] == SENTINEL_EMAIL
        assert payload["message"] == SENTINEL_MESSAGE

    def test_values_are_stripped(self, document):
        payload = report.build_payload(
            document,
            {
                "name": "  padded  ",
                "email": " a@b.cd ",
                "message": " hello ",
                "reason": " x ",
            },
        )

        assert payload["name"] == "padded"
        assert payload["email"] == "a@b.cd"
        assert payload["message"] == "hello"
        assert payload["reason"] == "x"

    def test_empty_submission_does_not_raise(self, document):
        assert report.build_payload(document, None)["name"] == ""


class TestGetReviewState:
    """``get_state(obj, default=None)`` is what copes with no workflow at all."""

    def test_returns_the_state(self, document):
        assert report.get_review_state(document) == "published"

    def test_returns_none_without_workflow(self, document, without_workflow):
        assert report.get_review_state(document) is None


class TestBuildBody:
    def test_holds_every_technical_field(self, document):
        payload = report.build_payload(document, SUBMITTED)

        body = report.build_body(document, payload)

        assert SENTINEL_TITLE in body
        assert document.absolute_url() in body
        assert document.UID() in body
        assert "Document" in body
        assert "published" in body

    def test_holds_the_reason_and_the_message(self, document):
        payload = report.build_payload(document, SUBMITTED)

        body = report.build_body(document, payload)

        assert REASON_TITLE in body
        assert SENTINEL_MESSAGE in body

    def test_holds_the_reporter_details(self, document):
        payload = report.build_payload(document, SUBMITTED)

        body = report.build_body(document, payload)

        assert SENTINEL_NAME in body
        assert SENTINEL_EMAIL in body

    def test_holds_the_userid_of_an_authenticated_report(self, document):
        payload = report.build_payload(document, SUBMITTED)

        assert payload["userid"] in report.build_body(document, payload)

    def test_unknown_reason_token_falls_back_on_the_token(self, document):
        payload = report.build_payload(document, {**SUBMITTED, "reason": "vanished"})

        assert "vanished" in report.build_body(document, payload)

    def test_missing_review_state_does_not_raise(self, document, without_workflow):
        payload = report.build_payload(document, SUBMITTED)

        body = report.build_body(document, payload)

        assert report.MISSING_VALUE in body


class TestBuildSubject:
    def test_comes_from_the_record(self, registry, document):
        registry[SUBJECT_TEMPLATE] = "Sentinel subject about ${title}"

        assert (
            report.build_subject(document) == f"Sentinel subject about {SENTINEL_TITLE}"
        )

    def test_falls_back_on_the_translated_default(self, registry, document):
        registry[SUBJECT_TEMPLATE] = ""

        expected = report.translate(DEFAULT_SUBJECT_TEMPLATE).replace(
            "${title}", SENTINEL_TITLE
        )
        assert report.build_subject(document) == expected
        assert SENTINEL_TITLE in report.build_subject(document)

    def test_falls_back_when_the_record_is_none(self, registry, document):
        registry[SUBJECT_TEMPLATE] = None

        assert SENTINEL_TITLE in report.build_subject(document)


class TestGetRecipients:
    def test_reads_them_through_the_adapter(self, recipients, document):
        assert report.get_recipients(document) == [SENTINEL_RECIPIENT]

    def test_is_empty_without_any(self, registry, document):
        registry[RECIPIENTS] = []
        registry["plone.email_from_address"] = ""

        assert report.get_recipients(document) == []


class TestSendProblemReport:
    def test_mail_goes_to_the_configured_recipients(
        self, recipients, mailhost, document
    ):
        assert send_problem_report(document, SUBMITTED) is True

        assert SENTINEL_RECIPIENT in header(sent_message(mailhost), "To")

    def test_mail_carries_the_composed_subject(
        self, registry, recipients, mailhost, document
    ):
        registry[SUBJECT_TEMPLATE] = "Sentinel subject about ${title}"

        send_problem_report(document, SUBMITTED)

        assert header(sent_message(mailhost), "Subject") == (
            f"Sentinel subject about {SENTINEL_TITLE}"
        )

    def test_mail_carries_the_composed_body(self, recipients, mailhost, document):
        send_problem_report(document, SUBMITTED)

        body = body_of(sent_message(mailhost))

        assert SENTINEL_TITLE in body
        assert document.absolute_url() in body
        assert document.UID() in body
        assert "Document" in body
        assert "published" in body
        assert REASON_TITLE in body
        assert SENTINEL_MESSAGE in body

    def test_body_labels_are_not_mistaken_for_headers(
        self, recipients, mailhost, document
    ):
        """The body is a MIMEText, so ``Title: ...`` stays in the payload."""
        send_problem_report(document, SUBMITTED)

        message = sent_message(mailhost)

        assert message["Title"] is None
        assert message["UID"] is None

    def test_nothing_is_sent_without_a_recipient(self, registry, mailhost, document):
        registry[RECIPIENTS] = []
        registry["plone.email_from_address"] = ""

        assert send_problem_report(document, SUBMITTED) is False
        assert list(mailhost.messages) == []

    def test_no_event_is_fired_without_a_recipient(
        self, registry, mailhost, received, document
    ):
        registry[RECIPIENTS] = []
        registry["plone.email_from_address"] = ""

        send_problem_report(document, SUBMITTED)

        assert received == []

    def test_event_is_fired_once(self, recipients, mailhost, received, document):
        send_problem_report(document, SUBMITTED)

        assert len(received) == 1
        assert received[0].object is document

    def test_event_payload_keys_are_the_contract(
        self, recipients, mailhost, received, document
    ):
        """Asserted literally: subscribers.audit reads ``reason`` and ``userid``."""
        send_problem_report(document, SUBMITTED)

        data = received[0].data

        assert data["reason"] == REASON_TOKEN
        assert data["review_state"] == "published"
        assert data["userid"] == api.user.get_current().getId()
        assert data["name"] == SENTINEL_NAME
        assert data["email"] == SENTINEL_EMAIL
        assert data["message"] == SENTINEL_MESSAGE

    def test_event_payload_userid_is_falsy_for_anonymous(
        self, recipients, mailhost, received, portal, document
    ):
        """A wrong ``userid`` degrades the audit log to authenticated=False."""
        logout()
        try:
            send_problem_report(document, SUBMITTED)
        finally:
            login(portal, TEST_USER_NAME)

        assert not received[0].data["userid"]

    def test_works_on_content_without_workflow(
        self, recipients, mailhost, received, document, without_workflow
    ):
        assert send_problem_report(document, SUBMITTED) is True
        assert received[0].data["review_state"] is None
        assert report.MISSING_VALUE in body_of(sent_message(mailhost))

    def test_works_on_unpublished_content(self, recipients, mailhost, portal):
        with api.env.adopt_user(SITE_OWNER_NAME):
            draft = api.content.create(
                container=portal,
                type="Document",
                id="draft-document",
                title="A draft",
            )

        assert send_problem_report(draft, SUBMITTED) is True
        assert "private" in body_of(sent_message(mailhost))


class TestIsReportAvailable:
    def test_true_with_a_recipient_for_an_authenticated_user(
        self, recipients, document
    ):
        assert report.is_report_available(document) is True

    def test_false_without_a_recipient(self, registry, document):
        registry[RECIPIENTS] = []
        registry["plone.email_from_address"] = ""

        assert report.is_report_available(document) is False
