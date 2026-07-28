"""Tests for the IProblemReportedEvent object event."""

from imio.reportproblem.events import ProblemReportedEvent
from imio.reportproblem.interfaces import IProblemReportedEvent
from plone import api
from plone.app.testing import SITE_OWNER_NAME
from zope.component import getGlobalSiteManager
from zope.event import notify
from zope.interface.interfaces import IObjectEvent
from zope.interface.verify import verifyObject

import pytest


#: The form hands over the reason *token*, never its translated title: that is
#: what lets a consumer route or count reports by reason.  Not a credential,
#: whatever ``flake8-bandit`` makes of the name.
REASON_TOKEN = "content-error"  # noqa: S105


@pytest.fixture()
def document(portal):
    """A published document to report a problem on."""
    with api.env.adopt_user(SITE_OWNER_NAME):
        doc = api.content.create(
            container=portal,
            type="Document",
            id="doc-report-problem",
            title="A document with a problem",
        )
        api.content.transition(obj=doc, transition="publish")
    return doc


@pytest.fixture()
def payload(document):
    """A report payload as the form builds it."""
    return {
        "reason": REASON_TOKEN,
        "review_state": api.content.get_state(document),
        "name": "Jean Dupont",
        "email": "jean.dupont@example.invalid",
        "message": "The third paragraph is wrong.",
        "userid": None,
    }


@pytest.fixture()
def received():
    """Collect every IProblemReportedEvent fired while the test runs."""
    events = []

    def handler(event):
        events.append(event)

    site_manager = getGlobalSiteManager()
    site_manager.registerHandler(handler, (IProblemReportedEvent,))
    yield events
    site_manager.unregisterHandler(handler, (IProblemReportedEvent,))


class TestProblemReportedEvent:
    def test_provides_interface(self, document, payload):
        event = ProblemReportedEvent(document, payload)

        assert IProblemReportedEvent.providedBy(event)
        assert verifyObject(IProblemReportedEvent, event)

    def test_is_an_object_event(self, document, payload):
        event = ProblemReportedEvent(document, payload)

        assert IObjectEvent.providedBy(event)
        assert event.object is document
        assert event.data is payload

    def test_notify_reaches_subscriber(self, document, payload, received):
        notify(ProblemReportedEvent(document, payload))

        assert len(received) == 1
        assert received[0].object is document
        assert received[0].data == payload

    def test_payload_round_trips_reason_token(self, document, payload, received):
        notify(ProblemReportedEvent(document, payload))

        assert received[0].data["reason"] == REASON_TOKEN

    def test_payload_round_trips_publication_state(self, document, payload, received):
        notify(ProblemReportedEvent(document, payload))

        assert received[0].data["review_state"] == "published"
        assert received[0].data["review_state"] == api.content.get_state(document)

    def test_notify_does_not_reach_subscriber_for_other_objects(
        self, document, payload, received
    ):
        """A plain object event must not be mistaken for a problem report."""
        from zope.interface.interfaces import ObjectEvent

        notify(ObjectEvent(document))

        assert received == []
