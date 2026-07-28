"""Read access to the ``IReportProblemSettings`` records.

Every helper here tolerates a missing record, and even a missing registry: the
package has to survive being imported -- and its viewlets, forms and
vocabularies have to survive being looked up -- before its GenericSetup profile
has been applied.
"""

from imio.reportproblem.constants import DISPLAY_MODE_MODAL
from imio.reportproblem.constants import DISPLAY_MODES
from imio.reportproblem.interfaces import IReportProblemSettings
from plone.registry.interfaces import IRegistry
from zope.component import queryUtility


#: Dotted prefix every ``IReportProblemSettings`` record key is built from.
RECORD_PREFIX = IReportProblemSettings.__identifier__


def _record_name(name):
    """Return the full registry key of the ``name`` record."""
    return f"{RECORD_PREFIX}.{name}"


def get_setting(name, default=None):
    """Return a IReportProblemSettings record, tolerating a missing registry."""
    registry = queryUtility(IRegistry)
    if registry is None:
        return default
    return registry.get(_record_name(name), default)


def get_wording(name, fallback):
    """Return the configured wording, or the translated fallback Message.

    ``fallback`` is one of the DEFAULT_* Messages from constants. Returns the
    stripped registry value when it is non-empty, and ``fallback`` otherwise.

    Keeping the fallback out of the registry is what keeps it translatable:
    a value shipped in ``registry.xml`` would be frozen in a single language
    for every site, including the sites that never opened the control panel.
    A value typed in the control panel, on the other hand, is used as is.
    """
    value = get_setting(name)
    if isinstance(value, str):
        value = value.strip()
        if value:
            return value
    return fallback


def get_display_mode():
    """Return the configured form display mode (``modal`` or ``page``)."""
    mode = get_setting("form_display_mode", DISPLAY_MODE_MODAL)
    if mode not in DISPLAY_MODES:
        return DISPLAY_MODE_MODAL
    return mode
