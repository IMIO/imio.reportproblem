"""Tests for the audit logging of problem reports.

The point of these tests is the GDPR property: the audit log is a
long-retention file, and it must hold no personal data about the reporter.
The payload below therefore carries distinctive sentinel strings for the
reporter's name, email address and message, so that the negative assertions
actually mean something.
"""

from imio.reportproblem.events import ProblemReportedEvent
from imio.reportproblem.subscribers import audit
from plone import api
from plone.app.testing import SITE_OWNER_NAME
from plone.app.testing import TEST_USER_ID
from zope.event import notify

import logging
import pytest


#: A reason token, not a credential, whatever ``flake8-bandit`` makes of it.
REASON_TOKEN = "content-error"  # noqa: S105

#: Personal data the payload carries.  None of it may show up in the log line.
REPORTER_NAME = "ZZSENTINELNAMEZZ Jean Dupont"
REPORTER_EMAIL = "zzsentinelmailzz@example.invalid"
REPORTER_MESSAGE = "ZZSENTINELBODYZZ the third paragraph gives out my address."

SENTINELS = ("ZZSENTINELNAMEZZ", "zzsentinelmailzz", "ZZSENTINELBODYZZ")


@pytest.fixture()
def fingerpointing_logger_name():
    """Name of the logger fingerpointing writes to.

    Skips cleanly when the optional ``audit`` extra is not installed.
    """
    config = pytest.importorskip("collective.fingerpointing.config")
    return config.PROJECTNAME


@pytest.fixture()
def document(portal):
    """A published document to report a problem on."""
    with api.env.adopt_user(SITE_OWNER_NAME):
        doc = api.content.create(
            container=portal,
            type="Document",
            id="doc-audit-problem",
            title="A document with a problem",
        )
        api.content.transition(obj=doc, transition="publish")
    return doc


@pytest.fixture()
def payload(document):
    """An anonymous report payload, as the form builds it."""
    return {
        "reason": REASON_TOKEN,
        "review_state": api.content.get_state(document),
        "name": REPORTER_NAME,
        "email": REPORTER_EMAIL,
        "message": REPORTER_MESSAGE,
        "userid": None,
    }


class TestAuditExtras:
    """The metadata-only line built out of a report, dependency or not."""

    def test_holds_content_uid_and_path(self, document, payload):
        extras = audit.build_audit_extras(document, payload)

        assert f"uid={document.UID()}" in extras
        assert f"path={'/'.join(document.getPhysicalPath())}" in extras

    def test_holds_portal_type(self, document, payload):
        extras = audit.build_audit_extras(document, payload)

        assert "portal_type=Document" in extras

    def test_holds_reason_token(self, document, payload):
        extras = audit.build_audit_extras(document, payload)

        assert f"reason={REASON_TOKEN}" in extras

    def test_holds_authenticated_flag_for_anonymous(self, document, payload):
        extras = audit.build_audit_extras(document, payload)

        assert "authenticated=False" in extras

    def test_holds_authenticated_flag_for_authenticated(self, document, payload):
        payload["userid"] = TEST_USER_ID

        extras = audit.build_audit_extras(document, payload)

        assert "authenticated=True" in extras

    def test_omits_the_reporter_userid(self, document, payload):
        """The userid is reduced to a boolean, it is not written out."""
        payload["userid"] = TEST_USER_ID

        extras = audit.build_audit_extras(document, payload)

        assert TEST_USER_ID not in extras

    def test_omits_reporter_personal_data(self, document, payload):
        extras = audit.build_audit_extras(document, payload)

        assert REPORTER_NAME not in extras
        assert REPORTER_EMAIL not in extras
        assert REPORTER_MESSAGE not in extras
        for sentinel in SENTINELS:
            assert sentinel not in extras

    def test_omits_every_personal_payload_key(self, document, payload):
        """Whatever sits under a personal key stays out of the log line."""
        extras = audit.build_audit_extras(document, payload)

        for key in audit.PERSONAL_PAYLOAD_KEYS:
            assert key in payload, f"the test payload should carry {key!r}"
            assert str(payload[key]) not in extras
            assert f"{key}=" not in extras

    def test_stays_on_a_single_line(self, document, payload):
        """A free-text reason must not be able to inject a log line."""
        payload["reason"] = "content\nerror injected=yes"

        extras = audit.build_audit_extras(document, payload)

        assert "\n" not in extras

    def test_survives_an_empty_payload(self, document):
        extras = audit.build_audit_extras(document, {})

        assert "reason=-" in extras
        assert "authenticated=False" in extras


class TestAuditSubscriber:
    """End to end, through the subscriber registered by fingerpointing.zcml."""

    def _audit_lines(self, caplog, logger_name):
        return [
            record.getMessage()
            for record in caplog.records
            if record.name == logger_name
        ]

    def test_subscriber_writes_an_audit_line(
        self, fingerpointing_logger_name, document, payload, caplog
    ):
        logger_name = fingerpointing_logger_name

        with caplog.at_level(logging.INFO, logger=logger_name):
            notify(ProblemReportedEvent(document, payload))

        lines = self._audit_lines(caplog, logger_name)
        assert lines, "the subscriber did not write anything to the audit log"
        line = lines[-1]
        assert f"action={audit.AUDIT_ACTION}" in line
        assert document.UID() in line
        assert "/".join(document.getPhysicalPath()) in line
        assert "portal_type=Document" in line
        assert f"reason={REASON_TOKEN}" in line
        assert "authenticated=False" in line

    def test_audit_line_holds_no_personal_data(
        self, fingerpointing_logger_name, document, payload, caplog
    ):
        logger_name = fingerpointing_logger_name

        with caplog.at_level(logging.INFO, logger=logger_name):
            notify(ProblemReportedEvent(document, payload))

        line = self._audit_lines(caplog, logger_name)[-1]
        assert REPORTER_NAME not in line
        assert REPORTER_EMAIL not in line
        assert REPORTER_MESSAGE not in line
        for sentinel in SENTINELS:
            assert sentinel not in line
