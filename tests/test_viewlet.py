"""Tests for the ``report-problem-button`` viewlet and its two display modes.

The button and the form share one single display condition,
``report.is_report_available``, so the security relevant branch -- an anonymous
visitor with no captcha available -- is tested here too, and unconditionally:
the flag is patched on the module, exactly as ``test_captcha`` does it.
"""

from imio.reportproblem import captcha
from imio.reportproblem.browser import viewlets as viewlets_module
from imio.reportproblem.browser.viewlets import ReportProblemButtonViewlet
from imio.reportproblem.constants import DEFAULT_BUTTON_LABEL
from imio.reportproblem.constants import DISPLAY_MODE_MODAL
from imio.reportproblem.constants import DISPLAY_MODE_PAGE
from imio.reportproblem.constants import FORM_CONTENT_SELECTOR
from imio.reportproblem.interfaces import IBrowserLayer
from imio.reportproblem.interfaces import IReportProblemSettings
from lxml import html
from plone import api
from plone.app.testing import login
from plone.app.testing import logout
from plone.app.testing import TEST_USER_NAME
from plone.dexterity.schema import SCHEMA_CACHE
from plone.registry.interfaces import IRegistry
from Products.Five.browser import BrowserView
from zope.component import getUtility
from zope.component import queryMultiAdapter
from zope.i18n import translate
from zope.interface import alsoProvides
from zope.viewlet.interfaces import IViewlet
from zope.viewlet.interfaces import IViewletManager

import json
import pytest


PREFIX = IReportProblemSettings.__identifier__
RECIPIENTS = f"{PREFIX}.recipients"
BUTTON_LABEL = f"{PREFIX}.button_label"
DISPLAY_MODE = f"{PREFIX}.form_display_mode"
PORTAL_EMAIL = "plone.email_from_address"

BEHAVIOR_NAME = "imio.reportproblem.reportable"
VIEWLET_NAME = "report-problem-button"
MANAGER_NAME = "plone.belowcontentbody"
OTHER_MANAGER_NAME = "plone.abovecontentbody"
FORM_VIEW_URL = "/@@report-problem"

SENTINEL_RECIPIENT = "sentinel-recipient@example.invalid"
SENTINEL_LABEL = "Sentinel button label"

MODAL_CLASS = "pat-plone-modal"
MODAL_ATTRIBUTE = "data-pat-plone-modal"


@pytest.fixture
def registry(portal):
    """The site registry, with the add-on records guaranteed present."""
    registry = getUtility(IRegistry)
    if RECIPIENTS not in registry:
        registry.registerInterface(IReportProblemSettings)
    return registry


@pytest.fixture
def recipients(registry):
    registry[RECIPIENTS] = [SENTINEL_RECIPIENT]
    return [SENTINEL_RECIPIENT]


@pytest.fixture
def no_recipient(registry):
    """No recipient at all, the portal email fallback included."""
    registry[RECIPIENTS] = []
    registry[PORTAL_EMAIL] = ""


@pytest.fixture
def request_with_layers(http_request):
    """The integration request, marked as a traversal would mark it."""
    alsoProvides(http_request, IBrowserLayer)
    return http_request


@pytest.fixture
def reportable(portal, get_fti):
    """Enable the behavior on ``Document`` for the duration of the test."""
    fti = get_fti("Document")
    original = tuple(fti.behaviors)
    fti.behaviors = (*original, BEHAVIOR_NAME)
    SCHEMA_CACHE.invalidate(fti)
    yield fti
    fti.behaviors = original
    SCHEMA_CACHE.invalidate(fti)


@pytest.fixture
def document(portal, reportable):
    """A document carrying the marker behavior."""
    with api.env.adopt_roles(["Manager"]):
        return api.content.create(
            container=portal,
            type="Document",
            id="reportable-document",
            title="A reportable document",
        )


@pytest.fixture
def plain_document(portal):
    """A document *without* the behavior: no button must be offered on it."""
    with api.env.adopt_roles(["Manager"]):
        return api.content.create(
            container=portal,
            type="Document",
            id="plain-document",
            title="A plain document",
        )


@pytest.fixture
def anonymous(portal):
    """Run the test as an anonymous visitor."""
    logout()
    yield
    login(portal, TEST_USER_NAME)


@pytest.fixture
def with_captcha(monkeypatch):
    """Pretend the ``captcha`` extra is installed, whatever this install has."""
    monkeypatch.setattr(captcha, "HAS_CAPTCHA", True)


@pytest.fixture
def without_captcha(monkeypatch):
    """Pretend the ``captcha`` extra is not installed."""
    monkeypatch.setattr(captcha, "HAS_CAPTCHA", False)


@pytest.fixture
def modal_mode(registry):
    registry[DISPLAY_MODE] = DISPLAY_MODE_MODAL


@pytest.fixture
def page_mode(registry):
    registry[DISPLAY_MODE] = DISPLAY_MODE_PAGE


def get_manager(context, request, name=MANAGER_NAME):
    """Return the viewlet manager ``name``, as a page template would get it."""
    view = BrowserView(context, request)
    return queryMultiAdapter((context, request, view), IViewletManager, name=name)


def get_viewlet(context, request, name=MANAGER_NAME):
    """Return the button viewlet, or None when it is not registered."""
    manager = get_manager(context, request, name=name)
    if manager is None:  # pragma: no cover
        return None
    return queryMultiAdapter(
        (context, request, manager.__parent__, manager),
        IViewlet,
        name=VIEWLET_NAME,
    )


def get_viewlet_names(context, request, name=MANAGER_NAME):
    """Return the names of the viewlets the manager ``name`` holds."""
    manager = get_manager(context, request, name=name)
    manager.update()
    return [viewlet.__name__ for viewlet in manager.viewlets]


def render(context, request):
    """Update and render the button viewlet, as its manager would."""
    viewlet = get_viewlet(context, request)
    viewlet.update()
    return viewlet.render()


def link_of(rendered):
    """Return the single link of the rendered viewlet."""
    parsed = html.fromstring(rendered)
    links = parsed.xpath('//a[contains(@class, "report-problem-link")]')
    assert len(links) == 1
    return links[0]


class TestRegistration:
    def test_registered_below_the_content_body(self, document, request_with_layers):
        assert VIEWLET_NAME in get_viewlet_names(document, request_with_layers)

    def test_is_the_viewlet_class(self, document, request_with_layers):
        assert isinstance(
            get_viewlet(document, request_with_layers), ReportProblemButtonViewlet
        )

    def test_not_registered_in_another_manager(self, document, request_with_layers):
        """``plone.belowcontentbody`` and nowhere else."""
        assert (
            get_viewlet(document, request_with_layers, name=OTHER_MANAGER_NAME) is None
        )

    def test_not_registered_without_the_behavior(
        self, plain_document, request_with_layers
    ):
        """A content type opts in through the behavior, and only through it."""
        assert get_viewlet(plain_document, request_with_layers) is None

    def test_not_held_by_the_manager_without_the_behavior(
        self, plain_document, request_with_layers
    ):
        assert VIEWLET_NAME not in get_viewlet_names(
            plain_document, request_with_layers
        )


class TestAvailability:
    """One single condition, shared with the form: ``is_report_available``."""

    def test_renders_the_button_when_available(
        self, recipients, document, request_with_layers
    ):
        assert "report-problem-link" in render(document, request_with_layers)

    def test_is_available_follows_the_predicate(
        self, recipients, document, request_with_layers
    ):
        assert get_viewlet(document, request_with_layers).is_available() is True

    def test_renders_nothing_without_a_recipient(
        self, no_recipient, document, request_with_layers
    ):
        assert render(document, request_with_layers) == ""

    def test_renders_nothing_when_the_predicate_refuses(
        self, monkeypatch, recipients, document, request_with_layers
    ):
        """The guard sits in Python, so an override of the markup cannot open it."""
        monkeypatch.setattr(
            viewlets_module, "is_report_available", lambda context: False
        )

        assert render(document, request_with_layers) == ""

    def test_renders_when_the_predicate_accepts(
        self, monkeypatch, no_recipient, document, request_with_layers
    ):
        monkeypatch.setattr(
            viewlets_module, "is_report_available", lambda context: True
        )

        assert "report-problem-link" in render(document, request_with_layers)

    def test_anonymous_without_a_captcha_gets_no_button(
        self, recipients, document, request_with_layers, anonymous, without_captcha
    ):
        """The security relevant branch: no captcha, no anonymous form, no button."""
        assert render(document, request_with_layers) == ""

    def test_anonymous_with_a_captcha_gets_the_button(
        self, recipients, document, request_with_layers, anonymous, with_captcha
    ):
        assert "report-problem-link" in render(document, request_with_layers)

    def test_authenticated_is_unaffected_by_the_missing_captcha(
        self, recipients, document, request_with_layers, without_captcha
    ):
        assert "report-problem-link" in render(document, request_with_layers)


class TestMarkup:
    """The CSS hooks ``plonetheme.deliberations`` styles, and nothing more."""

    @pytest.fixture
    def rendered(self, recipients, document, request_with_layers):
        return render(document, request_with_layers)

    def test_the_wrapper_carries_its_class(self, rendered):
        assert html.fromstring(rendered).get("class") == "report-problem-viewlet"

    def test_the_link_carries_its_class(self, rendered):
        assert "report-problem-link" in link_of(rendered).get("class").split()

    def test_no_icon_element_is_shipped(self, rendered):
        """The theme injects its icon in CSS; a generic add-on ships no font."""
        assert html.fromstring(rendered).xpath("//i") == []

    def test_a_single_link_is_rendered(self, rendered):
        assert len(html.fromstring(rendered).xpath("//a")) == 1

    def test_the_href_points_at_the_form_view(
        self, rendered, document, request_with_layers
    ):
        assert (
            link_of(rendered).get("href") == f"{document.absolute_url()}{FORM_VIEW_URL}"
        )


class TestLabel:
    def test_the_label_comes_from_the_record(
        self, registry, recipients, document, request_with_layers
    ):
        registry[BUTTON_LABEL] = SENTINEL_LABEL

        link = link_of(render(document, request_with_layers))

        assert link.text_content().strip() == SENTINEL_LABEL

    def test_the_label_falls_back_on_the_translated_default(
        self, registry, recipients, document, request_with_layers
    ):
        registry[BUTTON_LABEL] = ""

        link = link_of(render(document, request_with_layers))

        assert link.text_content().strip() == translate(DEFAULT_BUTTON_LABEL)

    def test_the_msgid_never_leaks(
        self, registry, recipients, document, request_with_layers
    ):
        """An untranslated Message would show ``report_problem_button``."""
        registry[BUTTON_LABEL] = None

        assert "report_problem_button" not in render(document, request_with_layers)

    def test_the_configured_label_is_also_the_aria_label(
        self, registry, recipients, document, request_with_layers
    ):
        """Accessibility never drifts from what is displayed."""
        registry[BUTTON_LABEL] = SENTINEL_LABEL

        link = link_of(render(document, request_with_layers))

        assert link.get("aria-label") == SENTINEL_LABEL
        assert link.get("aria-label") == link.text_content().strip()

    def test_the_fallback_label_is_also_the_aria_label(
        self, registry, recipients, document, request_with_layers
    ):
        registry[BUTTON_LABEL] = ""

        link = link_of(render(document, request_with_layers))

        assert link.get("aria-label") == translate(DEFAULT_BUTTON_LABEL)
        assert link.get("aria-label") == link.text_content().strip()


class TestModalMode:
    """The form is loaded over AJAX by mockup's ``pat-plone-modal``."""

    @pytest.fixture
    def link(self, modal_mode, recipients, document, request_with_layers):
        return link_of(render(document, request_with_layers))

    @pytest.fixture
    def options(self, link):
        """The pattern options, parsed rather than matched as a substring."""
        return json.loads(link.get(MODAL_ATTRIBUTE))

    def test_the_link_triggers_the_pattern(self, link):
        assert MODAL_CLASS in link.get("class").split()

    def test_the_options_are_valid_json(self, link):
        assert isinstance(json.loads(link.get(MODAL_ATTRIBUTE)), dict)

    def test_the_pattern_extracts_the_form_element(self, options):
        assert options["content"] == FORM_CONTENT_SELECTOR

    def test_the_modal_has_a_width(self, options):
        assert options["width"] == 600

    def test_the_response_redirect_is_followed_by_the_browser(self, options):
        """Or the confirmation is invisible: see ``viewlets.modal_options``."""
        assert options["actionOptions"]["redirectOnResponse"] is True

    def test_the_href_is_the_form_view(self, link, document):
        assert link.get("href") == f"{document.absolute_url()}{FORM_VIEW_URL}"


class TestPageMode:
    """The very same link, without the pattern class."""

    @pytest.fixture
    def link(self, page_mode, recipients, document, request_with_layers):
        return link_of(render(document, request_with_layers))

    def test_the_pattern_class_is_absent(self, link):
        assert MODAL_CLASS not in link.get("class").split()

    def test_the_link_still_carries_its_own_class(self, link):
        assert "report-problem-link" in link.get("class").split()

    def test_no_pattern_options_are_emitted(self, link):
        assert link.get(MODAL_ATTRIBUTE) is None

    def test_the_href_is_the_form_view(self, link, document):
        assert link.get("href") == f"{document.absolute_url()}{FORM_VIEW_URL}"

    def test_the_href_is_the_same_as_in_modal_mode(
        self, registry, recipients, document, request_with_layers
    ):
        """One single view: only the class and the options differ."""
        registry[DISPLAY_MODE] = DISPLAY_MODE_PAGE
        page_href = link_of(render(document, request_with_layers)).get("href")
        registry[DISPLAY_MODE] = DISPLAY_MODE_MODAL
        modal_href = link_of(render(document, request_with_layers)).get("href")

        assert page_href == modal_href
