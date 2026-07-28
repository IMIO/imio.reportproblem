"""Optional hCaptcha support, isolated behind a single import.

``plone.formwidget.hcaptcha`` ships in the ``captcha`` extra, not in the
dependencies.  Its mere presence turns the captcha on, exactly as
``collective.fingerpointing`` turns the audit logging on: no setting to flip,
no conditional ZCML, no warning to render in the control panel.

Two consequences, both deliberate:

* **Authenticated users never get a captcha.**  It guards against automated
  anonymous submissions, and an account is already accountable -- the userid
  travels with the report, so the recipient can tell an internal report from a
  citizen's one.  There is no flag for this case, only this documentation.

* **Anonymous visitors fail closed.**  Without the extra there is no captcha,
  so the form is not offered to them at all.  It is the very same condition as
  a missing recipient, see ``report.is_report_available``.  The
  ``logger.warning`` below is the only trace of it at startup; the symptom on
  the site is explicit enough -- citizens simply never see the button.

A site wanting reCAPTCHA or a honeypot instead overrides the ``report-problem``
view on its own browser layer, which is a plain Plone mechanism and needs no
extension point here.
"""

from imio.reportproblem import _
from imio.reportproblem import logger
from plone.autoform import directives
from z3c.form import field
from zope import schema
from zope.component import queryMultiAdapter
from zope.interface import Interface


#: Name of the captcha field, in the schema and on the form alike.
CAPTCHA_FIELD_NAME = "captcha"

#: Name of the browser view ``plone.formwidget.hcaptcha`` registers to render
#: and to verify its widget.
CAPTCHA_VIEW_NAME = "hcaptcha"


try:
    # Imported from the package root, and not from the module the widget lives
    # in: it moved from ``plone.formwidget.hcaptcha.widget`` (1.x) to
    # ``plone.formwidget.hcaptcha.browser.widget`` (3.x), while this
    # re-export stayed put across both.
    from plone.formwidget.hcaptcha import HCaptchaFieldWidget

    HAS_CAPTCHA = True
except ImportError:
    HAS_CAPTCHA = False
    logger.warning(
        "plone.formwidget.hcaptcha is not importable: the problem report form "
        "is not offered to anonymous visitors. Install the 'captcha' extra "
        "(imio.reportproblem[captcha]) to let citizens report a problem."
    )


if HAS_CAPTCHA:

    class ICaptchaSchema(Interface):
        """The captcha field, defined only when the widget is importable.

        Kept in this module rather than next to the form schema so that the
        whole optional dependency -- the import, the field and its widget --
        sits behind one single condition.
        """

        directives.widget(CAPTCHA_FIELD_NAME, HCaptchaFieldWidget)

        captcha = schema.TextLine(
            title=_("report_problem_captcha", default="Verification"),
            description="",
            required=False,
        )

else:
    #: No field to add: the form simply never asks for a captcha.
    ICaptchaSchema = None


def is_captcha_available():
    """Return True when the hCaptcha widget is importable.

    A function rather than the bare ``HAS_CAPTCHA`` flag, so that every caller
    reads the value at call time: that is what lets a test exercise the
    fail-closed branch on an install that happens to have the extra, and the
    other way round.
    """
    return HAS_CAPTCHA


def get_captcha_fields():
    """Return the captcha ``z3c.form`` fields, or None without the extra.

    The ``plone.autoform`` directive above is only honoured when the schema
    goes through the autoform machinery, and the form appends these fields by
    hand in ``updateFields()``; the widget factory is therefore also assigned
    explicitly here, so the widget is the hCaptcha one either way.
    """
    if not is_captcha_available() or ICaptchaSchema is None:
        return None
    fields = field.Fields(ICaptchaSchema)
    fields[CAPTCHA_FIELD_NAME].widgetFactory = HCaptchaFieldWidget
    return fields


def verify_captcha(context, request):
    """Return True only when the submitted captcha checks out.

    Fail closed on every other outcome -- extra not installed, view not
    registered because the add-on's ZCML was not loaded, hCaptcha keys not
    configured, verification server unreachable.  A captcha that cannot be
    verified must never let a submission through.
    """
    if not is_captcha_available():
        return False
    view = queryMultiAdapter((context, request), name=CAPTCHA_VIEW_NAME)
    if view is None:
        logger.warning(
            "The '%s' view is not available: the captcha could not be "
            "verified and the submission was rejected.",
            CAPTCHA_VIEW_NAME,
        )
        return False
    try:
        return bool(view.verify())
    except Exception:
        # Typically a missing private key, or the verification server being
        # unreachable. Logged with its traceback, and rejected all the same.
        logger.exception("Verifying the captcha failed; submission rejected.")
        return False
