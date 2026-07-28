"""Events fired by the add-on."""

from imio.reportproblem.interfaces import IProblemReportedEvent
from zope.interface import implementer
from zope.interface.interfaces import ObjectEvent


@implementer(IProblemReportedEvent)
class ProblemReportedEvent(ObjectEvent):
    """A problem report has been sent successfully for an object.

    The add-on persists nothing.  It fires this event once the report went
    out and lets consumers hook whatever they need onto it -- opening a
    ticket, counting reports, storing them.  That is what keeps the package
    neutral.

    ``data`` is the report payload, a plain mapping.  It carries the reason
    *token* rather than its translated title, so a consumer can route or
    count reports by reason without this package having to store anything,
    along with the content's publication state, the reporter's details and
    message, and the userid when the report was authenticated.
    """

    def __init__(self, obj, data):
        super().__init__(obj)
        self.data = data
