"""The ``@@report-problem`` form.

One single view serves both display modes.  The modal loads it over AJAX and
extracts ``#report-problem-form`` from it; the standalone page renders the very
same markup, back link included.  Which of the two happens is decided by the
button's link -- with or without the ``pat-plone-modal`` class -- and never
here: nothing in this module knows or asks whether it is being rendered inside
a modal.

Three things follow from that, and they are the reason the template looks the
way it does:

* the title and the introduction sit *inside* the extracted element, so they
  show in both modes without duplicating anything;
* the back link sits *outside* it, so the modal does not pick it up while the
  page does;
* a ``pat-plone-modal`` link whose pattern fails to initialise stays a plain
  ``<a href>``, so the page mode is also the no-JavaScript fallback and there
  is no degradation to write.
"""

from imio.reportproblem import _
from imio.reportproblem import logger
from imio.reportproblem.captcha import CAPTCHA_FIELD_NAME
from imio.reportproblem.captcha import get_captcha_fields
from imio.reportproblem.captcha import is_captcha_available
from imio.reportproblem.captcha import verify_captcha
from imio.reportproblem.constants import DEFAULT_CONFIRMATION_MESSAGE
from imio.reportproblem.constants import DEFAULT_FORM_INTRO
from imio.reportproblem.constants import DEFAULT_FORM_TITLE
from imio.reportproblem.constants import FORM_CONTENT_ID
from imio.reportproblem.constants import REASONS_VOCABULARY
from imio.reportproblem.interfaces import is_email
from imio.reportproblem.report import is_report_available
from imio.reportproblem.report import send_problem_report
from imio.reportproblem.settings import get_wording
from plone import api
from plone.autoform.form import AutoExtensibleForm
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from Products.MailHost.MailHost import MailHostError
from Products.statusmessages.interfaces import IStatusMessage
from smtplib import SMTPException
from z3c.form import button
from z3c.form import form
from zope import schema
from zope.interface import Interface


#: Member properties the name and email fields are pre-filled from.
MEMBER_PROPERTIES = {"name": "fullname", "email": "email"}

#: Label of the form's own submit button.  Not the ``button_label`` record,
#: which names the *button on the content* that opens this form.
SEND_BUTTON_LABEL = _("report_problem_send_button", default="Send the report")

CAPTCHA_ERROR = _(
    "report_problem_captcha_error",
    default="The captcha validation was unsuccessful. Please retry by "
    "carefully following the instructions.",
)

SEND_ERROR = _(
    "report_problem_send_error",
    default="Your report could not be sent. Please try again later.",
)

UNAVAILABLE = _(
    "report_problem_unavailable",
    default="Reporting a problem is not available on this content.",
)


class IReportProblemForm(Interface):
    """What the reporter fills in, and nothing else.

    Every technical field of the report -- the content's title, URL, UID,
    portal type and publication state -- is composed server side by
    ``report.build_body``, out of the reporter's reach.
    """

    name = schema.TextLine(
        title=_("report_problem_field_name", default="Your name"),
        required=True,
    )

    email = schema.TextLine(
        title=_("report_problem_field_email", default="Your email address"),
        description=_(
            "report_problem_field_email_help",
            default="So that we can get back to you about your report.",
        ),
        required=True,
        constraint=is_email,
    )

    reason = schema.Choice(
        title=_("report_problem_field_reason", default="Reason"),
        vocabulary=REASONS_VOCABULARY,
        required=True,
    )

    message = schema.Text(
        title=_("report_problem_field_message", default="Message"),
        description=_(
            "report_problem_field_message_help",
            default="Describe the problem as precisely as you can.",
        ),
        required=True,
    )


class ReportProblemForm(AutoExtensibleForm, form.Form):
    """Report a problem on the content this view is looked up on.

    Registered for ``IProblemReportable`` with the plain ``View`` permission:
    whoever can see the content can report a problem about it, including on
    unpublished content, and no dedicated permission is created.  No leak
    follows from that -- an anonymous visitor who cannot see the content cannot
    see this form either.
    """

    schema = IReportProblemForm
    ignoreContext = True
    enable_form_tabbing = False
    css_class = "report-problem"
    template = ViewPageTemplateFile("templates/report_problem_form.pt")

    #: Checked by ``plone.app.z3cform``'s actions manager before a handler
    #: runs.  Turned on explicitly because this form writes nothing to the
    #: database, so ``plone.protect``'s automatic protection -- which triggers
    #: on a write -- would never look at it, and sending mail to a configured
    #: address is exactly the kind of side effect a third party site must not
    #: be able to trigger.  Setting it is also what makes the ``ploneform``
    #: macro emit the ``_authenticator`` hidden input, inside the ``form``
    #: element and therefore inside the element the modal extracts, so the
    #: token travels with an AJAX submission just as with a plain one.
    enableCSRFProtection = True

    #: False when the report is not offered at all -- see ``is_available``.
    #: The template then renders an explanation instead of the fields.
    available = True

    @property
    def label(self):
        return get_wording("form_title", DEFAULT_FORM_TITLE)

    @property
    def description(self):
        return get_wording("form_intro", DEFAULT_FORM_INTRO)

    @property
    def unavailable_message(self):
        return UNAVAILABLE

    @property
    def form_content_id(self):
        """DOM id of the element the modal extracts from this page."""
        return FORM_CONTENT_ID

    @property
    def context_url(self):
        """URL the back link points at, outside the extracted element."""
        return self.context.absolute_url()

    def is_available(self):
        """Return True when this form may be offered at all.

        Deliberately the same single condition as the button's: no recipient
        to send to, or an anonymous visitor with no captcha available, and the
        form is not offered.  Delegated to ``report.is_report_available`` so
        the button and the form can never disagree.
        """
        return is_report_available(self.context)

    def show_captcha(self):
        """Return True when the form asks for a captcha.

        Only anonymous visitors get one.  An authenticated account is already
        accountable and its userid travels with the report, so a captcha would
        buy nothing; see ``imio.reportproblem.captcha`` for the full rationale.
        """
        return is_captcha_available() and api.user.is_anonymous()

    def get_member_defaults(self):
        """Return the values the member's properties pre-fill the form with.

        Empty for an anonymous visitor.  Values stay editable: a manager
        reporting on behalf of a colleague, or from another address, only has
        to type over them.
        """
        if api.user.is_anonymous():
            return {}
        member = api.user.get_current()
        if member is None:  # pragma: no cover
            return {}
        values = {}
        for name, property_name in MEMBER_PROPERTIES.items():
            values[name] = member.getProperty(property_name, "") or ""
        return values

    def updateFields(self):
        super().updateFields()
        if not self.show_captcha():
            return
        captcha_fields = get_captcha_fields()
        if captcha_fields is not None:
            self.fields += captcha_fields

    def updateWidgets(self, prefix=None):
        super().updateWidgets(prefix=prefix)
        # Only fills what the request left empty, so a value the reporter
        # typed over survives a validation error.
        for name, value in self.get_member_defaults().items():
            widget = self.widgets.get(name)
            if widget is not None and not widget.value:
                widget.value = value

    def update(self):
        self.available = self.is_available()
        if not self.available:
            # Neither widgets nor actions: an unavailable form must not be
            # submittable either. The template renders an explanation.
            logger.info(
                "The problem report form is not offered on %s: no recipient "
                "is configured, or the visitor is anonymous and no captcha is "
                "available.",
                self.context_url,
            )
            return
        super().update()

    @button.buttonAndHandler(SEND_BUTTON_LABEL, name="send")
    def handle_send(self, action):
        data, errors = self.extractData()
        if errors:
            self.status = self.formErrorsMessage
            return

        if self.show_captcha() and not verify_captcha(self.context, self.request):
            self.status = CAPTCHA_ERROR
            return

        data.pop(CAPTCHA_FIELD_NAME, None)
        try:
            sent = send_problem_report(self.context, data)
        except (SMTPException, MailHostError, ValueError, RuntimeError):
            logger.exception(
                "Sending the problem report about %s failed.", self.context_url
            )
            self.status = SEND_ERROR
            return

        if not sent:
            # Should not happen: ``is_available`` already refused a form with
            # no recipient. Kept because the configuration may have changed
            # between the render and the submit.
            self.status = SEND_ERROR
            return

        IStatusMessage(self.request).add(
            get_wording("confirmation_message", DEFAULT_CONFIRMATION_MESSAGE)
        )
        # Redirected to the content on purpose, so the confirmation shows
        # there rather than inside the modal.
        self.request.response.redirect(self.context_url)
