"""Tests for the report problem control panel and its registry records."""

from imio.reportproblem.constants import DEFAULT_REASONS
from imio.reportproblem.constants import DISPLAY_MODE_MODAL
from imio.reportproblem.controlpanels.settings import ReportProblemSettingsEditForm
from imio.reportproblem.interfaces import IBrowserLayer
from imio.reportproblem.interfaces import IReportProblemSettings
from imio.reportproblem.interfaces import is_email
from imio.reportproblem.settings import RECORD_PREFIX
from plone import api
from plone.app.testing import setRoles
from plone.app.testing import TEST_USER_ID
from plone.registry.interfaces import IRegistry
from zope.component import getMultiAdapter
from zope.component import getUtility
from zope.interface import alsoProvides
from zope.schema.interfaces import ConstraintNotSatisfied
from zope.schema.interfaces import WrongContainedType

import pytest


CONFIGLET_ID = "imio.reportproblem.settings"
VIEW_NAME = "reportproblem-controlpanel"

WORDING_RECORDS = (
    "button_label",
    "form_title",
    "form_intro",
    "confirmation_message",
)


@pytest.fixture
def registry(portal):
    return getUtility(IRegistry)


class TestRegistryRecords:
    def test_every_record_is_created(self, registry):
        for name in IReportProblemSettings.names():
            assert f"{RECORD_PREFIX}.{name}" in registry.records

    def test_reasons_ship_the_defaults(self, registry):
        assert registry[f"{RECORD_PREFIX}.reasons"] == list(DEFAULT_REASONS)

    def test_subject_template_is_shipped(self, registry):
        assert registry[f"{RECORD_PREFIX}.subject_template"] == (
            "[Problem report] ${title}"
        )

    def test_form_display_mode_is_modal(self, registry):
        assert registry[f"{RECORD_PREFIX}.form_display_mode"] == DISPLAY_MODE_MODAL

    @pytest.mark.parametrize("name", WORDING_RECORDS)
    def test_wording_records_are_empty_after_install(self, registry, name):
        """Spec requirement: no wording is shipped, so the i18n catalog wins."""
        assert not registry[f"{RECORD_PREFIX}.{name}"]

    def test_recipients_is_empty_after_install(self, registry):
        assert registry[f"{RECORD_PREFIX}.recipients"] == []

    def test_privacy_url_is_empty_after_install(self, registry):
        assert registry[f"{RECORD_PREFIX}.privacy_url"] is None


class TestEmailConstraint:
    """``recipients.value_type`` carries ``constraint=is_email``.

    The GenericSetup import of the interface accepts it, but ``plone.registry``
    silently drops constraints while cloning the schema into persistent fields
    (``PersistentField.constraint`` is a ``DisallowedProperty``). Validation
    therefore happens where the user types: the control panel form builds its
    fields from the interface itself, constraint included.
    """

    def test_the_interface_field_validates_emails(self):
        field = IReportProblemSettings["recipients"]

        assert field.value_type.constraint is is_email
        field.validate(["someone@example.org"])
        with pytest.raises(WrongContainedType) as error:
            field.validate(["not-an-email"])
        assert isinstance(error.value.args[0][0], ConstraintNotSatisfied)

    def test_the_form_is_built_on_that_interface(self):
        assert ReportProblemSettingsEditForm.schema is IReportProblemSettings

    def test_the_persistent_record_does_not_enforce_it(self, registry):
        """Documented limitation, kept under test so a change gets noticed."""
        api.portal.set_registry_record(f"{RECORD_PREFIX}.recipients", ["not-an-email"])

        assert registry[f"{RECORD_PREFIX}.recipients"] == ["not-an-email"]


class TestConfiglet:
    def test_configlet_is_installed(self, controlpanel_actions):
        assert CONFIGLET_ID in controlpanel_actions


class TestControlPanelView:
    @pytest.fixture
    def view(self, portal, http_request):
        # setRoles rather than @pytest.mark.portal(roles=...): that marker is a
        # no-op on the pytest-plone 1.0.0a2 the Plone 6.1 constraints resolve,
        # so these tests were silently running without the Manager role there.
        setRoles(portal, TEST_USER_ID, ["Manager"])
        alsoProvides(http_request, IBrowserLayer)
        return getMultiAdapter((portal, http_request), name=VIEW_NAME)

    def test_view_is_registered(self, view):
        assert view is not None

    def test_view_renders(self, view):
        html = view()

        assert "Report a problem" in html
        assert "form.widgets.reasons" in html
        assert "form.widgets.form_display_mode" in html

    def test_form_exposes_every_setting(self, portal, http_request):
        alsoProvides(http_request, IBrowserLayer)
        form = ReportProblemSettingsEditForm(portal, http_request)
        form.update()

        assert set(IReportProblemSettings.names()).issubset(set(form.fields))
