"""Named vocabulary listing the reasons offered in the report form."""

from imio.reportproblem import _
from imio.reportproblem.settings import get_setting
from plone.i18n.normalizer.interfaces import IIDNormalizer
from zope.component import getUtility
from zope.interface import implementer
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.vocabulary import SimpleTerm
from zope.schema.vocabulary import SimpleVocabulary


@implementer(IVocabularyFactory)
class ReasonsVocabulary:
    """Build the reasons vocabulary from the control panel.

    Registered as a *named* utility rather than used as an inline source, for
    two reasons: an integrator can swap it out with a single ZCML utility
    override, and the factory receives the context, so a product may vary the
    reasons per content or per container -- reasons per institution, say --
    without this package having to plan for it.

    The label typed in the control panel is kept as the term title, wrapped in
    a ``Message`` of the package domain: it is translated when the catalog
    ships a matching msgid -- the case for the reasons shipped by default --
    and rendered as typed otherwise. That is the accepted limitation of a
    through-the-web configurable vocabulary.

    The token cannot be the label itself, which holds spaces and accents and
    is therefore unfit as an HTML form value, so it is derived from the label
    with the ``idnormalizer``.
    """

    def __call__(self, context=None):
        normalizer = getUtility(IIDNormalizer)
        terms = []
        seen = set()
        for raw_label in get_setting("reasons") or []:
            label = (raw_label or "").strip()
            if not label:
                continue
            token = normalizer.normalize(label)
            if not token or token in seen:
                continue
            seen.add(token)
            terms.append(SimpleTerm(value=token, token=token, title=_(label)))
        return SimpleVocabulary(terms)


#: Utility registered under ``constants.REASONS_VOCABULARY``.
ReasonsVocabularyFactory = ReasonsVocabulary()
