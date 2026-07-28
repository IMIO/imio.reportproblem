"""The ``report-problem-button`` viewlet.

The button that opens the ``@@report-problem`` form, rendered in
``plone.belowcontentbody`` on any content carrying ``IProblemReportable``.

**One single view, two display modes.**  Nothing here renders a form, and
nothing here knows about two implementations: the modal and the standalone page
are the very same ``@@report-problem`` view, and the only thing that differs
between the two modes is this link.  In modal mode it carries mockup's
``pat-plone-modal`` class, which loads the view over AJAX and keeps the element
``FORM_CONTENT_SELECTOR`` names; in page mode the class is simply absent and the
browser follows the link.  The page mode is therefore also the no-JavaScript
fallback -- a ``pat-plone-modal`` link whose pattern does not initialise stays an
ordinary ``<a href>`` -- so there is no degradation to write.

**Fail closed, on one single condition.**  Whether the button shows is
``report.is_report_available``, which the form's own ``is_available`` calls too:
button and form can never disagree.  It already encodes ``is_enabled()``, a
resolvable recipient and, for an anonymous visitor, an available captcha.  That
condition is checked in ``render`` -- in Python, not in the template -- so a
``z3c.jbot`` override of the markup cannot accidentally open what the guard
rails close.
"""

from imio.reportproblem.constants import DEFAULT_BUTTON_LABEL
from imio.reportproblem.constants import DISPLAY_MODE_MODAL
from imio.reportproblem.constants import FORM_CONTENT_SELECTOR
from imio.reportproblem.report import is_report_available
from imio.reportproblem.settings import get_display_mode
from imio.reportproblem.settings import get_wording
from plone.app.layout.viewlets.common import ViewletBase
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.i18n import translate

import json


#: The view the button leads to, in both display modes.
FORM_VIEW_NAME = "report-problem"

#: CSS class of the link, and the one CSS hook computed here.
#: ``plonetheme.deliberations`` styles these exact names -- a wrapper
#: ``.report-problem-viewlet``, in the template, holding a link
#: ``.report-problem-link`` -- so renaming either loses the styling in
#: production.  The theme also injects its icon through a ``::before`` rule
#: guarded by ``:has(i)``, which is why the template ships no ``<i>`` of its
#: own: a generic add-on must not hard-code another package's icon font.
LINK_CLASS = "report-problem-link"

#: Mockup's own trigger class.  Present in modal mode, absent in page mode, and
#: that is the whole of the difference between the two modes.
MODAL_CLASS = "pat-plone-modal"

#: Width handed to the pattern, in pixels; jQuery turns the number into ``px``.
MODAL_WIDTH = 600


class ReportProblemButtonViewlet(ViewletBase):
    """Render the link that opens the problem report form.

    Deliberately thin: it computes a URL, a class and a label, and the template
    is minimal so a site can override it through ``z3c.jbot``.  Everything that
    decides *whether* the report is offered lives in
    ``report.is_report_available``.
    """

    index = ViewPageTemplateFile("templates/report_problem_button.pt")

    def is_available(self):
        """Return True when the button may be shown at all.

        The same single condition as the form's, delegated to the same helper:
        no recipient to send to, or an anonymous visitor with no captcha
        available, and neither the button nor the form is offered.
        """
        return is_report_available(self.context)

    def is_modal(self):
        """Return True when the form is configured to open in a modal."""
        return get_display_mode() == DISPLAY_MODE_MODAL

    @property
    def label(self):
        """Return the button's text, translated.

        ``button_label`` from the control panel, falling back on the add-on's
        own translated label.  Translated here rather than in the template
        because the very same string is also the link's ``aria-label``, and a
        ``Message`` left untranslated in an attribute would expose its msgid:
        the accessible name can never drift from what is displayed.
        """
        wording = get_wording("button_label", DEFAULT_BUTTON_LABEL)
        return translate(wording, context=self.request)

    @property
    def link_url(self):
        """Return the ``@@report-problem`` URL on this content.

        The same URL in both modes: in modal mode the pattern fetches it over
        AJAX, in page mode the browser goes to it.
        """
        return f"{self.context.absolute_url()}/@@{FORM_VIEW_NAME}"

    @property
    def link_class(self):
        """Return the link's classes, with mockup's trigger in modal mode."""
        if self.is_modal():
            return f"{LINK_CLASS} {MODAL_CLASS}"
        return LINK_CLASS

    def get_modal_options(self):
        """Return the options handed to ``pat-plone-modal``.

        ``content`` is the element the pattern extracts from the loaded view;
        the form template puts its back link outside of it on purpose, so the
        modal drops it while the standalone page shows it.

        ``actionOptions.redirectOnResponse`` is not decoration, see
        ``modal_options``.
        """
        return {
            "content": FORM_CONTENT_SELECTOR,
            "width": MODAL_WIDTH,
            "actionOptions": {"redirectOnResponse": True},
        }

    @property
    def modal_options(self):
        """Return the ``data-pat-plone-modal`` JSON, or None in page mode.

        None drops the attribute altogether, which is what keeps the page mode
        link an ordinary one.

        ``redirectOnResponse`` has to be turned on: the form redirects to the
        content with an ``IStatusMessage`` on success, and mockup's defaults
        (``redirectOnResponse: false``, ``displayInModal: true``) would follow
        that redirect over AJAX and redraw the modal from the content page,
        where ``FORM_CONTENT_SELECTOR`` no longer matches anything -- an empty
        modal, a page behind it that never reloads, and a confirmation the
        reporter never sees.
        """
        if not self.is_modal():
            return None
        return json.dumps(self.get_modal_options())

    def render(self):
        """Render the button, or nothing at all.

        The guard sits here, in Python, and not in the template: a ``z3c.jbot``
        override replaces the markup, never this condition.
        """
        if not self.is_available():
            return ""
        return super().render()
