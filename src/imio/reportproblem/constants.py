"""Shared constants."""

from imio.reportproblem import _


#: Name of the named vocabulary listing the reasons offered in the form.
REASONS_VOCABULARY = "imio.reportproblem.reasons"

#: The form is rendered in a modal window loaded over AJAX.
DISPLAY_MODE_MODAL = "modal"

#: The form is rendered as a standalone page, with a back link to the content.
DISPLAY_MODE_PAGE = "page"

DISPLAY_MODES = (DISPLAY_MODE_MODAL, DISPLAY_MODE_PAGE)

#: DOM id wrapping the part of the form the modal extracts from the page.
#: Anything that must show up on the standalone page but *not* in the modal
#: (typically the back link) has to live outside of this element.
FORM_CONTENT_ID = "report-problem-form"

FORM_CONTENT_SELECTOR = f"#{FORM_CONTENT_ID}"

#: The shipped reasons, declared through ``_()`` so that i18ndude extracts
#: them. The vocabulary translates a reason label at runtime, which a static
#: scan cannot see, and the shipped defaults have to be translated in FR and
#: NL -- a reason an administrator adds by hand stays in the language it was
#: typed in, which is the accepted limit of a through-the-web vocabulary.
DEFAULT_REASON_MESSAGES = (
    _("Content error"),
    _("Personal data"),
    _("Missing or unreadable annex"),
    _("Other"),
)

#: Reasons shipped in ``profiles/default/registry/main.xml``. Plain strings:
#: they are persisted in the registry, so they must not be ``Message``
#: instances. ``DEFAULT_REASON_MESSAGES`` above is the single source of truth.
DEFAULT_REASONS = tuple(str(message) for message in DEFAULT_REASON_MESSAGES)

#: Fallback wording, used whenever the matching registry record is empty.
#: Keeping the default out of the registry is what allows these to stay
#: translated: a value shipped in ``registry.xml`` would be frozen in a
#: single language for every site, including sites that never opened the
#: control panel.
DEFAULT_BUTTON_LABEL = _("report_problem_button", default="Report a problem")

DEFAULT_FORM_TITLE = _("report_problem_form_title", default="Report a problem")

DEFAULT_FORM_INTRO = _(
    "report_problem_form_intro",
    default="Spotted an error on this content? Tell us about it and we will "
    "look into it.",
)

DEFAULT_CONFIRMATION_MESSAGE = _(
    "report_problem_confirmation",
    default="Thank you, your report has been sent.",
)

DEFAULT_SUBJECT_TEMPLATE = _(
    "report_problem_subject",
    default="[Problem report] ${title}",
)
