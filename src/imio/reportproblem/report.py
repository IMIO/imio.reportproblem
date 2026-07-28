"""Composing and sending a problem report.

The sending logic lives in a plain function, ``send_problem_report``, and not
in the form handler: a REST endpoint for Volto is planned for 1.1 and has to
reuse it verbatim, payload keys and email body included.

Nothing here is persisted.  The email goes out, ``IProblemReportedEvent`` is
fired, and that is the whole of it -- consumers hook onto the event to open a
ticket, count reports or store them.
"""

from email.mime.text import MIMEText
from imio.reportproblem import _
from imio.reportproblem import logger
from imio.reportproblem.captcha import is_captcha_available
from imio.reportproblem.constants import DEFAULT_SUBJECT_TEMPLATE
from imio.reportproblem.constants import REASONS_VOCABULARY
from imio.reportproblem.events import ProblemReportedEvent
from imio.reportproblem.settings import get_wording
from imio.reportproblem.utils import get_report_config
from plone import api
from string import Template
from zope.component import queryUtility
from zope.event import notify
from zope.i18nmessageid import Message
from zope.schema.interfaces import IVocabularyFactory


#: Keys of the payload handed to ``IProblemReportedEvent``.  A cross-package
#: contract: ``subscribers.audit`` reads ``reason`` -- the reason *token* -- and
#: ``userid``, which is falsy for an anonymous report, and deliberately never
#: reads ``name``, ``email`` nor ``message``, which hold personal data.
#: Renaming any of these silently degrades the audit log.
PAYLOAD_KEYS = ("reason", "review_state", "userid", "name", "email", "message")

#: Rendered in the email body wherever a technical field has no value.
MISSING_VALUE = "-"

BODY_INTRO = _(
    "report_problem_body_intro",
    default="A problem has been reported on the following content.",
)

BODY_CONTENT_HEADING = _("report_problem_body_content", default="Content")

BODY_REPORTER_HEADING = _("report_problem_body_reporter", default="Report")

LABEL_CONTENT_TITLE = _("report_problem_body_label_title", default="Title")

LABEL_CONTENT_URL = _("report_problem_body_label_url", default="URL")

LABEL_CONTENT_UID = _("report_problem_body_label_uid", default="UID")

LABEL_CONTENT_TYPE = _("report_problem_body_label_type", default="Content type")

LABEL_REVIEW_STATE = _(
    "report_problem_body_label_review_state",
    default="Publication state",
)

LABEL_REASON = _("report_problem_body_label_reason", default="Reason")

LABEL_NAME = _("report_problem_body_label_name", default="Name")

LABEL_EMAIL = _("report_problem_body_label_email", default="Email address")

LABEL_USERID = _("report_problem_body_label_userid", default="User id")

LABEL_MESSAGE = _("report_problem_body_label_message", default="Message")


def translate(message):
    """Translate a Message, tolerating being called outside a portal.

    The email body is composed server side, for a recipient that is often a
    generic mailbox: its labels are translated, unlike the technical values
    they introduce.
    """
    if message is None:
        return ""
    if not isinstance(message, Message):
        return str(message)
    try:
        return api.portal.translate(message)
    except api.exc.PloneApiError:  # pragma: no cover
        return message.default or str(message)


def get_content_title(context):
    """Return the content's title, never raising."""
    title = getattr(context, "Title", None)
    if callable(title):
        title = title()
    return title or getattr(context, "title", "") or ""


def get_canonical_url(context):
    """Return the content's own URL, not the path it was reached through."""
    absolute_url = getattr(context, "absolute_url", None)
    return absolute_url() if callable(absolute_url) else ""


def get_uid(context):
    """Return the content's UID, or an empty string."""
    uid = getattr(context, "UID", None)
    return (uid() if callable(uid) else "") or ""


def get_review_state(context):
    """Return the publication state, or None for content with no workflow.

    ``default=None`` is what copes with content that has no workflow at all.
    The state is part of the report because the button shows on unpublished
    content too: the recipient has to understand why the link they received
    may ask them to authenticate instead of just opening.
    """
    try:
        return api.content.get_state(context, default=None)
    except api.exc.PloneApiError:  # pragma: no cover
        return None


def get_current_userid():
    """Return the acting userid, or None when the reporter is anonymous."""
    try:
        if api.user.is_anonymous():
            return None
        user = api.user.get_current()
    except api.exc.PloneApiError:  # pragma: no cover
        return None
    return user.getId() if user is not None else None


def get_reason_title(context, token):
    """Return the human readable reason for a token, falling back on it.

    The payload carries the token, which is what lets a consumer route or count
    reports; the email body shows the label, which is what a human reads.
    """
    if not token:
        return ""
    factory = queryUtility(IVocabularyFactory, name=REASONS_VOCABULARY)
    if factory is None:  # pragma: no cover
        return token
    try:
        term = factory(context).getTermByToken(token)
    except LookupError:
        # A reason removed from the control panel since the form was rendered.
        return token
    return translate(term.title) or token


def get_recipients(context):
    """Return the recipients of a report about ``context``.

    Resolved through the single call point, so the viewlet, the form and the
    sending can never disagree on whether a report is possible.
    """
    config = get_report_config(context)
    if config is None or not config.is_enabled():
        return []
    return list(config.get_recipients() or [])


def is_report_available(context):
    """Return True when a report may be offered on ``context``.

    Fail closed, on one single condition covering both cases: no recipient to
    send to, or an anonymous visitor with no captcha available.  Authenticated
    users have no captcha anyway and are unaffected.
    """
    if not get_recipients(context):
        return False
    return is_captcha_available() or not api.user.is_anonymous()


def build_payload(context, data):
    """Return the report payload, from what the reporter submitted.

    ``data`` holds only the four fields of the form -- ``name``, ``email``,
    ``reason`` and ``message``.  The technical fields are derived here and are
    never editable by the user: that is what makes this function equally usable
    from the form handler and from a REST endpoint.
    """
    data = data or {}
    return {
        "reason": (data.get("reason") or "").strip(),
        "review_state": get_review_state(context),
        "userid": get_current_userid(),
        "name": (data.get("name") or "").strip(),
        "email": (data.get("email") or "").strip(),
        "message": (data.get("message") or "").strip(),
    }


def build_subject(context):
    """Return the email subject, from the ``subject_template`` record.

    Falls back on the add-on's own translated default when the record is
    empty, which is what ``get_wording`` is for.
    """
    template = get_wording("subject_template", DEFAULT_SUBJECT_TEMPLATE)
    return Template(translate(template)).safe_substitute(
        title=get_content_title(context)
    )


def build_body(context, payload):
    """Return the plain text email body of a report.

    Composed server side, and always holding the content's title, its URL, its
    UID, its portal type and its publication state, plus the reason and the
    reporter's details and message.  None of those technical fields is
    editable by the reporter.
    """
    content_fields = (
        (LABEL_CONTENT_TITLE, get_content_title(context)),
        (LABEL_CONTENT_URL, get_canonical_url(context)),
        (LABEL_CONTENT_UID, get_uid(context)),
        (LABEL_CONTENT_TYPE, getattr(context, "portal_type", "")),
        (LABEL_REVIEW_STATE, payload.get("review_state")),
    )
    reporter_fields = (
        (LABEL_REASON, get_reason_title(context, payload.get("reason"))),
        (LABEL_NAME, payload.get("name")),
        (LABEL_EMAIL, payload.get("email")),
        (LABEL_USERID, payload.get("userid")),
    )
    lines = [translate(BODY_INTRO), "", f"{translate(BODY_CONTENT_HEADING)}:"]
    lines += [
        f"{translate(label)}: {value or MISSING_VALUE}"
        for label, value in content_fields
    ]
    lines += ["", f"{translate(BODY_REPORTER_HEADING)}:"]
    lines += [
        f"{translate(label)}: {value or MISSING_VALUE}"
        for label, value in reporter_fields
    ]
    lines += [
        "",
        f"{translate(LABEL_MESSAGE)}:",
        "",
        payload.get("message") or MISSING_VALUE,
    ]
    return "\n".join(lines)


def send_problem_report(context, data):
    """Send a problem report about ``context`` and fire the event.

    :param context: the content the report is about.
    :param data: what the reporter submitted -- ``name``, ``email``,
        ``reason`` (the vocabulary *token*) and ``message``.
    :return: True when the report went out, False when there was nobody to
        send it to.
    :raises: whatever the mail host raises. The event is fired only after a
        successful send, so a consumer never sees a report that never left.
    """
    recipients = get_recipients(context)
    if not recipients:
        logger.warning(
            "No recipient is configured for %s: the problem report was not "
            "sent. Set one in the 'Report a problem' control panel.",
            get_canonical_url(context) or context,
        )
        return False

    payload = build_payload(context, data)
    # A MIMEText rather than a plain string: the mail host parses a string
    # body as an RFC 822 message, and the body's first lines are ``Label:
    # value`` pairs that it would happily mistake for headers.
    body = MIMEText(build_body(context, payload), "plain", "utf-8")
    api.portal.send_email(
        recipient=recipients,
        subject=build_subject(context),
        body=body,
    )
    notify(ProblemReportedEvent(context, payload))
    return True
