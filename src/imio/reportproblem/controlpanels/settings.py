"""Control panel editing the site wide ``IReportProblemSettings`` records.

Scope is deliberately site global: the wording is never resolved per context.
Should per institution labels ever be needed, they belong in the
``IProblemReportConfig`` adapter -- which already receives the context -- not
in extra registry acrobatics.
"""

from imio.reportproblem import _
from imio.reportproblem.interfaces import IReportProblemSettings
from plone.app.registry.browser.controlpanel import ControlPanelFormWrapper
from plone.app.registry.browser.controlpanel import RegistryEditForm
from plone.z3cform import layout


class ReportProblemSettingsEditForm(RegistryEditForm):
    """Edit form built around the already registered settings interface.

    The fields come from ``IReportProblemSettings`` itself, so the
    ``constraint=is_email`` carried by ``recipients.value_type`` is enforced
    here even though ``plone.registry`` drops constraints when it clones the
    schema into persistent fields.
    """

    schema = IReportProblemSettings
    schema_prefix = None
    label = _("controlpanel_report_problem_title", default="Report a problem")
    description = _(
        "controlpanel_report_problem_description",
        default="Site wide settings of the problem report form. Leave a "
        "wording field empty to keep the add-on's own translated label.",
    )


ReportProblemSettingsControlPanel = layout.wrap_form(
    ReportProblemSettingsEditForm,
    ControlPanelFormWrapper,
)
