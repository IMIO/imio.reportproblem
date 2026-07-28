"""The FR and NL catalogs must actually resolve at runtime.

Source labels are English; French and Dutch live only in the catalogs. These
tests fail if a catalog stops being shipped, stops being compiled, or loses an
entry -- which would silently fall back to English in production.
"""

from imio.reportproblem.constants import DEFAULT_BUTTON_LABEL
from imio.reportproblem.constants import DEFAULT_CONFIRMATION_MESSAGE
from imio.reportproblem.constants import DEFAULT_FORM_TITLE
from imio.reportproblem.constants import DEFAULT_REASON_MESSAGES
from zope.i18n import translate

import pytest


TRANSLATED_WORDING = {
    "fr": {
        DEFAULT_BUTTON_LABEL: "Signaler un problème",
        DEFAULT_FORM_TITLE: "Signaler un problème",
        DEFAULT_CONFIRMATION_MESSAGE: "Merci, votre signalement a été envoyé.",
    },
    "nl": {
        DEFAULT_BUTTON_LABEL: "Een probleem melden",
        DEFAULT_FORM_TITLE: "Een probleem melden",
        DEFAULT_CONFIRMATION_MESSAGE: "Bedankt, uw melding is verzonden.",
    },
}

TRANSLATED_REASONS = {
    "fr": [
        "Erreur de contenu",
        "Données personnelles",
        "Annexe manquante ou illisible",
        "Autre",
    ],
    "nl": [
        "Inhoudelijke fout",
        "Persoonsgegevens",
        "Ontbrekende of onleesbare bijlage",
        "Andere",
    ],
}


class TestTranslations:
    @pytest.mark.parametrize("language", ["fr", "nl"])
    def test_wording_defaults_are_translated(self, integration, language):
        """The fallback wording must be translated, not left in English."""
        for message, expected in TRANSLATED_WORDING[language].items():
            assert translate(message, target_language=language) == expected

    @pytest.mark.parametrize("language", ["fr", "nl"])
    def test_shipped_reasons_are_translated(self, integration, language):
        """The reasons shipped in registry.xml must be translated.

        A reason an administrator types by hand cannot be, which is the
        accepted limit of a through-the-web vocabulary -- but the four we
        ship have no excuse.
        """
        translated = [
            translate(message, target_language=language)
            for message in DEFAULT_REASON_MESSAGES
        ]

        assert translated == TRANSLATED_REASONS[language]

    def test_english_is_the_source_language(self, integration):
        """Untranslated lookups fall back to the English msgid."""
        assert translate(DEFAULT_BUTTON_LABEL, target_language="en") == (
            "Report a problem"
        )

    @pytest.mark.parametrize("language", ["fr", "nl"])
    def test_an_unknown_reason_falls_back_to_what_was_typed(
        self, integration, language
    ):
        """A reason with no catalog entry is shown exactly as typed."""
        from imio.reportproblem import _

        typed = "Un motif ajouté à la main"

        assert translate(_(typed), target_language=language) == typed
