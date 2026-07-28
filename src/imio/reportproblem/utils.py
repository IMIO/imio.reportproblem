"""Helpers shared by the viewlet, the form and the adapters."""

from imio.reportproblem.interfaces import IProblemReportConfig
from imio.reportproblem.settings import get_setting
from plone import api
from zope.interface.interfaces import ComponentLookupError


__all__ = ("get_registry_value", "get_report_config", "get_setting")


def get_report_config(context):
    """Return the ``IProblemReportConfig`` adapter for ``context``.

    Single call point for the whole add-on: the viewlet uses it to decide
    whether to offer the button, and the form uses it to send. No resolution
    logic is duplicated between the two, so a button can never show for a form
    that would then fail to send.

    :param context: the content the report would be about.
    :return: an ``IProblemReportConfig`` adapter, or None when no adapter is
        registered at all. The package registers a default one on ``*``, so
        None only happens when that registration has been removed.
    """
    return IProblemReportConfig(context, None)


def get_registry_value(name, default=None):
    """Return the registry record ``name``, or ``default``.

    Never raises: a record that has not been created yet -- typically because
    the profile has not been applied -- must not make the add-on explode.
    """
    try:
        return api.portal.get_registry_record(name, default=default)
    except (ComponentLookupError, KeyError):
        return default


# ``get_setting`` is re-exported from ``settings`` rather than reimplemented
# here: two helpers with the same name and the same semantics in two modules
# is a trap for whoever comes next. ``settings`` owns the record access,
# ``utils`` owns the adapter lookup.
