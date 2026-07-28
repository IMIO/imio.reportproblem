"""Adapters resolving the applicable problem report configuration."""

from imio.reportproblem.interfaces import IProblemReportConfig
from imio.reportproblem.utils import get_registry_value
from imio.reportproblem.utils import get_setting
from plone import api
from zope.component import adapter
from zope.interface import implementer
from zope.interface import Interface


@implementer(IProblemReportConfig)
@adapter(Interface)
class ProblemReportConfig:
    """Default, site wide problem report configuration.

    Registered on ``*`` (``zope.interface.Interface``) on purpose, and *not*
    on ``IProblemReportable``: a consumer package registers its own adapter on
    a more specific interface -- its own content type or its own marker -- and
    wins the lookup naturally, with no ``overrides.zcml`` and no dependency on
    the ZCML load order.

    The adapter is authoritative: it resolves the configuration, it does not
    merge it. The fallback chain (the control panel, then the portal's
    ``email_from_address``) lives here rather than in the callers, so a
    consumer keeps it by subclassing this class and calling ``super()``::

        @implementer(IProblemReportConfig)
        @adapter(IMyContent)
        class MyReportConfig(ProblemReportConfig):
            def get_recipients(self):
                email = self.context.institution_email
                return [email] if email else super().get_recipients()

    A consumer that does not call ``super()`` replaces the chain entirely --
    silently merging its recipients with the site wide ones would ship
    citizens' reports to a global address without the product asking for it.
    """

    def __init__(self, context):
        self.context = context

    def is_enabled(self):
        """Return True if reporting is offered on this content.

        Always True by default: no filtering on the publication state, the
        type or the roles. A product wanting another behaviour -- hiding the
        button on drafts, restricting it to some categories, disabling it for
        a period -- overrides this method in its own adapter, without touching
        the viewlet nor its registration.
        """
        return True

    def get_recipients(self):
        """Return the list of recipient email addresses.

        The ``recipients`` record of the control panel, falling back on the
        portal's ``email_from_address``. Always a list, possibly empty.
        """
        recipients = [
            address.strip()
            for address in get_setting("recipients") or []
            if address and address.strip()
        ]
        if recipients:
            return recipients
        fallback = self.get_portal_email()
        return [fallback] if fallback else []

    def get_privacy_url(self):
        """Return the privacy policy URL, or None when unset."""
        url = get_setting("privacy_url") or ""
        return url.strip() or None

    def get_portal_email(self):
        """Return the portal's ``email_from_address``, or None."""
        email = get_registry_value("plone.email_from_address")
        if not email:
            try:
                portal = api.portal.get()
            except api.exc.CannotGetPortalError:
                portal = None
            email = getattr(portal, "email_from_address", None)
        return (email or "").strip() or None
