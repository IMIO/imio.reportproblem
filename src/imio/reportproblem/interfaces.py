"""Module where all interfaces, events and exceptions live."""

from imio.reportproblem import _
from imio.reportproblem.constants import DEFAULT_REASONS
from imio.reportproblem.constants import DISPLAY_MODE_MODAL
from imio.reportproblem.constants import DISPLAY_MODE_PAGE
from zope import schema
from zope.interface import Attribute
from zope.interface import Interface
from zope.interface.interfaces import IObjectEvent
from zope.publisher.interfaces.browser import IDefaultBrowserLayer

import re


class IBrowserLayer(IDefaultBrowserLayer):
    """Marker interface that defines a browser layer."""


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_email(value):
    """Return True when ``value`` looks like an email address."""
    return bool(EMAIL_RE.match((value or "").strip()))


class IProblemReportable(Interface):
    """Marker interface for content a problem can be reported on.

    Applied through the ``imio.reportproblem.reportable`` behavior, which
    carries no schema on purpose: a report is transient, there is nothing to
    store on the content itself.
    """


class IProblemReportConfig(Interface):
    """Resolve the problem report configuration for a given content."""

    def is_enabled():
        """Return True if reporting is offered on this content."""

    def get_recipients():
        """Return the list of recipient email addresses."""

    def get_privacy_url():
        """Return the privacy policy URL, or None."""


class IProblemReportedEvent(IObjectEvent):
    """A problem report has been sent successfully for an object."""

    data = Attribute(
        "Mapping holding the report payload: the reason *token*, the "
        "content's publication state, the reporter's details and message, "
        "and the userid for an authenticated report."
    )


class IReportProblemSettings(Interface):
    """Site wide settings for imio.reportproblem."""

    recipients = schema.List(
        title=_("Recipients"),
        description=_(
            "Default email addresses receiving the reports. An adapter "
            "registered by another package may override them."
        ),
        value_type=schema.TextLine(title=_("Email address"), constraint=is_email),
        required=False,
        default=[],
        missing_value=[],
    )

    reasons = schema.List(
        title=_("Reasons"),
        description=_(
            "Reasons offered in the form. A reason is translated when the "
            "package ships a translation for it, and shown as typed "
            "otherwise."
        ),
        value_type=schema.TextLine(title=_("Reason")),
        required=True,
        default=list(DEFAULT_REASONS),
    )

    privacy_url = schema.TextLine(
        title=_("Privacy policy URL"),
        required=False,
        default=None,
    )

    subject_template = schema.TextLine(
        title=_("Subject template"),
        description=_("Template of the email subject. ${title} is substituted."),
        required=False,
        default=None,
    )

    button_label = schema.TextLine(
        title=_("Button label"),
        description=_(
            "Leave empty to use the add-on's own translated label. A value "
            "typed here is used as is, in the language it was typed in. It "
            "is used both as the button text and as its aria-label."
        ),
        required=False,
        default=None,
    )

    form_title = schema.TextLine(
        title=_("Form title"),
        description=_("Leave empty to use the add-on's own translated title."),
        required=False,
        default=None,
    )

    form_intro = schema.Text(
        title=_("Form introduction"),
        description=_("Leave empty to use the add-on's own translated text."),
        required=False,
        default=None,
    )

    confirmation_message = schema.Text(
        title=_("Confirmation message"),
        description=_("Leave empty to use the add-on's own translated message."),
        required=False,
        default=None,
    )

    form_display_mode = schema.Choice(
        title=_("Form display mode"),
        description=_(
            "Whether the form opens in a modal window or as a full page. "
            "Fall back to the page mode if the captcha misbehaves in the "
            "modal."
        ),
        values=[DISPLAY_MODE_MODAL, DISPLAY_MODE_PAGE],
        required=True,
        default=DISPLAY_MODE_MODAL,
    )
