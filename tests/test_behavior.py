"""Tests for the imio.reportproblem.reportable behavior."""

from imio.reportproblem.interfaces import IProblemReportable
from plone import api
from plone.behavior.interfaces import IBehavior
from plone.dexterity.schema import SCHEMA_CACHE
from zope.component import getUtility
from zope.component import queryUtility

import pytest


#: Public name, referenced from the FTI XML of other packages.
BEHAVIOR_NAME = "imio.reportproblem.reportable"


def _create(portal, portal_type, identifier):
    with api.env.adopt_roles(["Manager"]):
        return api.content.create(
            container=portal,
            type=portal_type,
            id=identifier,
            title=identifier,
        )


def _enable(fti):
    """Enable the behavior on ``fti`` and return its original behavior list."""
    original = tuple(fti.behaviors)
    fti.behaviors = (*original, BEHAVIOR_NAME)
    SCHEMA_CACHE.invalidate(fti)
    return original


def _restore(fti, behaviors):
    fti.behaviors = behaviors
    SCHEMA_CACHE.invalidate(fti)


class TestBehaviorRegistration:
    def test_registered_by_name(self, portal):
        """The short name is public API: DELIBE-326 uses it in its FTI XML."""
        assert queryUtility(IBehavior, name=BEHAVIOR_NAME) is not None

    def test_registered_by_interface_identifier(self, portal):
        name = IProblemReportable.__identifier__
        assert queryUtility(IBehavior, name=name) is not None

    def test_provides_the_marker_interface(self, portal):
        registration = getUtility(IBehavior, name=BEHAVIOR_NAME)
        assert registration.interface is IProblemReportable
        assert registration.marker is IProblemReportable

    def test_has_no_schema(self, portal):
        """A report is transient: nothing is stored on the content."""
        registration = getUtility(IBehavior, name=BEHAVIOR_NAME)
        assert registration.factory is None

    def test_title_and_description(self, portal):
        registration = getUtility(IBehavior, name=BEHAVIOR_NAME)
        assert registration.title == "Report a problem"
        assert registration.description == "Adds a report button on this content type"

    def test_not_enabled_by_default(self, get_behaviors):
        """Opt in: the integrator enables it per type in the control panel."""
        assert BEHAVIOR_NAME not in get_behaviors("Document")


class TestBehaviorEnabled:
    @pytest.fixture
    def fti(self, get_fti):
        fti = get_fti("Document")
        original = _enable(fti)
        yield fti
        _restore(fti, original)

    def test_can_be_enabled_on_a_dexterity_type(self, fti):
        assert BEHAVIOR_NAME in fti.behaviors

    def test_instances_provide_the_marker(self, portal, fti):
        document = _create(portal, "Document", "reportable-document")
        assert IProblemReportable.providedBy(document)

    def test_other_types_are_untouched(self, portal, fti):
        news_item = _create(portal, "News Item", "plain-news-item")
        assert not IProblemReportable.providedBy(news_item)

    def test_existing_content_needs_no_migration(self, portal, get_fti):
        """The marker is resolved dynamically, so no content is walked."""
        document = _create(portal, "Document", "pre-existing-document")
        assert not IProblemReportable.providedBy(document)

        fti = get_fti("Document")
        original = _enable(fti)
        try:
            assert IProblemReportable.providedBy(document)
        finally:
            _restore(fti, original)

    def test_disabling_removes_the_marker(self, portal, get_fti):
        fti = get_fti("Document")
        original = _enable(fti)
        document = _create(portal, "Document", "temporary-document")
        assert IProblemReportable.providedBy(document)
        _restore(fti, original)
        assert not IProblemReportable.providedBy(document)
