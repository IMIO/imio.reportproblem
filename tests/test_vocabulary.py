"""Tests for the reasons named vocabulary."""

from imio.reportproblem.constants import DEFAULT_REASONS
from imio.reportproblem.constants import REASONS_VOCABULARY
from imio.reportproblem.settings import RECORD_PREFIX
from plone import api
from zope.component import getUtility
from zope.i18n import translate
from zope.i18nmessageid import Message
from zope.schema.interfaces import IVocabularyFactory

import pytest


REASONS_RECORD = f"{RECORD_PREFIX}.reasons"

#: A label holding both an accent and a space, unfit as an HTML form value.
ACCENTED_LABEL = "Café façade error"


@pytest.fixture
def factory(portal):
    return getUtility(IVocabularyFactory, REASONS_VOCABULARY)


class TestReasonsVocabulary:
    def test_factory_is_registered(self, factory):
        assert IVocabularyFactory.providedBy(factory)

    def test_default_reasons_are_offered(self, portal, factory):
        vocabulary = factory(portal)

        assert [term.title for term in vocabulary] == list(DEFAULT_REASONS)

    def test_default_tokens(self, portal, factory):
        vocabulary = factory(portal)

        assert [term.token for term in vocabulary] == [
            "content-error",
            "personal-data",
            "missing-or-unreadable-annex",
            "other",
        ]

    def test_value_equals_token(self, portal, factory):
        for term in factory(portal):
            assert term.value == term.token

    def test_token_is_normalized(self, portal, factory):
        """A label with an accent *and* a space still yields a clean token."""
        api.portal.set_registry_record(REASONS_RECORD, [ACCENTED_LABEL])

        vocabulary = factory(portal)

        assert [term.token for term in vocabulary] == ["cafe-facade-error"]
        for term in vocabulary:
            assert " " not in term.token
            assert term.token.isascii()

    def test_title_keeps_the_original_label(self, portal, factory):
        api.portal.set_registry_record(REASONS_RECORD, [ACCENTED_LABEL])

        term = next(iter(factory(portal)))

        assert term.title == ACCENTED_LABEL

    def test_title_is_a_message_in_the_package_domain(self, portal, factory):
        api.portal.set_registry_record(REASONS_RECORD, [ACCENTED_LABEL])

        term = next(iter(factory(portal)))

        assert isinstance(term.title, Message)
        assert term.title.domain == "imio.reportproblem"

    def test_untranslated_label_is_shown_as_typed(self, portal, factory):
        """A reason typed by an administrator has no msgid, so it shows as is."""
        api.portal.set_registry_record(REASONS_RECORD, ["A hand typed reason"])

        term = next(iter(factory(portal)))

        assert translate(term.title, target_language="nl") == "A hand typed reason"

    def test_follows_registry_changes(self, portal, factory):
        api.portal.set_registry_record(REASONS_RECORD, ["Broken link", "Typo"])

        vocabulary = factory(portal)

        assert [term.token for term in vocabulary] == ["broken-link", "typo"]
        assert [term.title for term in vocabulary] == ["Broken link", "Typo"]

    @pytest.mark.portal(roles=["Manager"])
    def test_accepts_a_context_argument(self, portal, factory):
        document = api.content.create(
            container=portal, type="Document", id="doc", title="Doc"
        )

        assert len(factory(document).by_token) == len(DEFAULT_REASONS)

    def test_context_is_optional(self, portal, factory):
        assert len(factory().by_token) == len(DEFAULT_REASONS)
        assert len(factory(None).by_token) == len(DEFAULT_REASONS)

    def test_empty_and_duplicate_labels_are_skipped(self, portal, factory):
        api.portal.set_registry_record(
            REASONS_RECORD, ["Other", "", "   ", " Other ", "Content error"]
        )

        vocabulary = factory(portal)

        assert [term.token for term in vocabulary] == ["other", "content-error"]
