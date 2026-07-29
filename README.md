<div align="center">
    <h1 align="center">imio.reportproblem</h1>
</div>
<div align="center">
[![PyPI](https://img.shields.io/pypi/v/imio.reportproblem)](https://pypi.org/project/imio.reportproblem/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/imio.reportproblem)](https://pypi.org/project/imio.reportproblem/)
[![PyPI - Wheel](https://img.shields.io/pypi/wheel/imio.reportproblem)](https://pypi.org/project/imio.reportproblem/)
[![PyPI - License](https://img.shields.io/pypi/l/imio.reportproblem)](https://pypi.org/project/imio.reportproblem/)
[![PyPI - Status](https://img.shields.io/pypi/status/imio.reportproblem)](https://pypi.org/project/imio.reportproblem/)


[![PyPI - Plone Versions](https://img.shields.io/pypi/frameworkversions/plone/imio.reportproblem)](https://pypi.org/project/imio.reportproblem/)

[![CI](https://github.com/IMIO/imio.reportproblem/actions/workflows/main.yml/badge.svg)](https://github.com/IMIO/imio.reportproblem/actions/workflows/main.yml)
![Code Style](https://img.shields.io/badge/Code%20Style-Black-000000)

[![GitHub contributors](https://img.shields.io/github/contributors/IMIO/imio.reportproblem)](https://github.com/IMIO/imio.reportproblem)
[![GitHub Repo stars](https://img.shields.io/github/stars/IMIO/imio.reportproblem?style=social)](https://github.com/IMIO/imio.reportproblem)

</div>

Report a problem on Plone content: on the content types where the behavior is
enabled, a "Report a problem" button opens a form whose result is emailed to
configured recipients.

It exists because visitors and editors often have no way to flag a problem on
one specific page — a content error, unmasked personal data (GDPR), a missing
annex, something published by mistake.

## Features

- A marker behavior, `imio.reportproblem.reportable`, enabled per content type.
- A `@@report-problem` form, offered either in a modal window or as a full page.
- A viewlet `report-problem-button` in `plone.belowcontentbody`, with minimal
  markup that is easy to override (`z3c.jbot` compatible).
- A site-wide control panel: recipients, reasons, wording, display mode.
- Two extension points, so a consumer package can decide *who* receives a
  report and *what happens* after it is sent — see [Extending](#extending).
- Optional hCaptcha protection and optional audit logging, both as extras.
- The add-on **persists nothing**: reports are emailed and announced through an
  event. Storing, ticketing or counting them is a consumer's business.

## Compatibility

> [!IMPORTANT]
> **Version 1.0 is Classic UI only.** There is no Volto/React component and no
> REST endpoint. The sending logic is deliberately isolated in
> `imio.reportproblem.report.send_problem_report(context, data)` so that a REST
> endpoint can be added in 1.1 without duplicating anything.

Plone 6.0, 6.1 and 6.2 on Python 3.10 to 3.13.

## Installation

Install `imio.reportproblem` with `pip`:

```shell
pip install imio.reportproblem
```

Then install the add-on in Site Setup, or apply the
`imio.reportproblem:default` GenericSetup profile.

### Extras

The two optional dependencies are extras. **Installing the package is what
turns the corresponding feature on** — there is no setting to flip.

| Extra | Pulls in | Effect |
| --- | --- | --- |
| `captcha` | `plone.formwidget.hcaptcha` | Adds an hCaptcha field to the form for anonymous users. |
| `audit` | `collective.fingerpointing` | Logs every sent report to the audit log. |
| `all` | both of the above | |

```shell
pip install "imio.reportproblem[all]"
```

> [!WARNING]
> **Without the `captcha` extra, the form is not offered to anonymous users at
> all.** This is deliberate — fail closed rather than expose an unprotected
> anonymous form. A warning is logged at startup. So if citizens cannot see the
> button, the `captcha` extra is missing. Authenticated users are unaffected:
> they never get a captcha, because an authenticated account is already
> accountable.

The four installation configurations (no extra, `captcha`, `audit`, `all`) are
each exercised in CI.

## Enabling it on a content type

Enable the **Report a problem** behavior on the types you want, either in the
Dexterity control panel or from your own GenericSetup profile:

```xml
<property name="behaviors" purge="false">
  <element value="imio.reportproblem.reportable"/>
</property>
```

Behavior marker interfaces are resolved dynamically by `FTIAwareSpecification`,
so **existing content needs no migration** when you enable it.

## Configuration

Site Setup → **Report a problem** (`@@reportproblem-controlpanel`), stored in
`plone.app.registry` under `imio.reportproblem.interfaces.IReportProblemSettings`:

| Record | Purpose |
| --- | --- |
| `recipients` | Default recipient addresses, validated one by one. |
| `reasons` | The reasons offered in the form. |
| `privacy_url` | Link to the privacy policy. |
| `subject_template` | Email subject template; `${title}` is substituted. |
| `button_label` | Button text — also used as its `aria-label`. |
| `form_title` | Form title. |
| `form_intro` | Text shown above the form. |
| `confirmation_message` | Shown after a successful send. |
| `form_display_mode` | `modal` (default) or `page`. |

### Wording: empty means "translated default"

`button_label`, `form_title`, `form_intro` and `confirmation_message` ship
**empty on purpose**. While a field is empty the add-on shows its own label from
the i18n catalog, so it is translated. As soon as you type a value, that value
is used verbatim, in the one language you typed it in.

This is the opposite of `reasons`, which *does* ship defaults — an empty
vocabulary would make the form unusable.

### Reasons and translation

The reasons are configurable through the web, so they inevitably escape the
package's `.po` files. The convention: a reason is translated when a matching
msgid exists in the `imio.reportproblem` domain, and shown exactly as typed
otherwise. The four shipped defaults are translated in FR and NL; a reason an
administrator adds by hand appears in the language it was typed in.

Form tokens are derived from the label with `plone.i18n`'s `idnormalizer`, since
labels contain spaces and accents.

### Display mode

`modal` loads the form over AJAX with the Mockup `pat-plone-modal` pattern;
`page` renders it as a standalone page with a back link. It is the **same view**
either way — only the link changes, and a modal link whose pattern fails to
initialise stays an ordinary link, which is also the no-JavaScript fallback.

Switch to `page` if the captcha misbehaves inside the modal.

## Extending

### `IProblemReportConfig` — who receives a report

Resolves the applicable configuration for a given content:

```python
class IProblemReportConfig(Interface):
    def is_enabled(): ...
    def get_recipients(): ...
    def get_privacy_url(): ...
```

The default adapter is registered on `*`, **not** on `IProblemReportable`. That
matters: register yours on a more specific interface — your own content type or
your own marker — and it wins the lookup naturally, with no `overrides.zcml`
and no dependency on ZCML load order.

The adapter is **authoritative: it does not merge.** The fallback chain (control
panel, then the portal's `email_from_address`) lives in the default adapter, so
subclass it and call `super()` to keep it:

```python
from imio.reportproblem.adapters import ProblemReportConfig
from imio.reportproblem.interfaces import IProblemReportConfig


@implementer(IProblemReportConfig)
@adapter(IMyContent)
class MyReportConfig(ProblemReportConfig):
    def get_recipients(self):
        email = self._institution_email()
        return [email] if email else super().get_recipients()
```

If you do not call `super()`, your recipients are the only ones used. Merging
silently would ship citizens' reports to a global address your product never
asked for — bad for noise, worse for GDPR.

These are **methods, not properties**: a partial override reads unambiguously,
and a subclass that forgets a decorator cannot silently mask a value.

`is_enabled()` returns `True` by default — no filtering on publication state,
type or role. Override it to *restrict* the button (hide it on drafts, limit it
to some categories, disable it for a period). Note the asymmetry: the full
display condition is `is_enabled()` **and** a resolvable recipient **and**, for
anonymous visitors, an available captcha. **A product can restrict what is
shown; it cannot open what the guard rails close.**

Resolve it through the single entry point, never by adapting by hand:

```python
from imio.reportproblem.utils import get_report_config

config = get_report_config(context)
```

### `IProblemReportedEvent` — what happens next

An object event fired after a successful send. Hook onto it to open a ticket,
build statistics, or store the report:

```python
@adapter(IProblemReportedEvent)
def my_handler(event):
    event.object  # the content the report is about
    event.data["reason"]  # the reason *token*, not its translated title
```

`data` carries `reason` (token), `review_state`, `userid` (empty when
anonymous), `name`, `email` and `message`. The token is what lets you route or
count reports by reason without this package storing anything.

### Audit logging and GDPR

With the `audit` extra, the add-on ships one consumer of its own event: a
`collective.fingerpointing` subscriber.

> [!IMPORTANT]
> The audit line contains **no personal data about the reporter** — only the
> content's UID and path, its `portal_type`, the reason token, and whether the
> report was authenticated. An audit log is kept for a long time; writing a
> citizen's name, email or message into it would create an unmanaged parallel
> database. (`collective.fingerpointing` adds the acting user and IP itself, as
> it always does.)

### Replacing the captcha

A site wanting reCAPTCHA or a honeypot overrides the form view on its own
browser layer — a standard Plone mechanism that needs no extension point here.

## Translations

This product has been translated into French and Dutch. Source labels are in
English.

## Contribute

- [Issue tracker](https://github.com/IMIO/imio.reportproblem/issues)
- [Source code](https://github.com/IMIO/imio.reportproblem/)

### Prerequisites ✅

-   An [operating system](https://6.docs.plone.org/install/create-project-cookieplone.html#prerequisites-for-installation) that runs all the requirements mentioned.
-   [uv](https://6.docs.plone.org/install/create-project-cookieplone.html#uv)
-   [Make](https://6.docs.plone.org/install/create-project-cookieplone.html#make)
-   [Git](https://6.docs.plone.org/install/create-project-cookieplone.html#git)
-   [Docker](https://docs.docker.com/get-started/get-docker/) (optional)

### Installation 🔧

1.  Clone this repository, then change your working directory.

    ```shell
    git clone git@github.com:IMIO/imio.reportproblem.git
    cd imio.reportproblem
    ```

2.  Install this code base.

    ```shell
    make install
    ```

Useful targets: `make test`, `make test-coverage`, `make check` (format then
lint), `make i18n` (update the catalogs), `make start`.

### Add features using `plonecli` or `bobtemplates.plone`

This package provides markers as strings (`<!-- extra stuff goes here -->`) that are compatible with [`plonecli`](https://github.com/plone/plonecli) and [`bobtemplates.plone`](https://github.com/plone/bobtemplates.plone).
These markers act as hooks to add all kinds of subtemplates, including behaviors, control panels, upgrade steps, or other subtemplates from `plonecli`.

To run `plonecli` with configuration to target this package, run the following command.

```shell
make add <template_name>
```

For example, you can add a content type to your package with the following command.

```shell
make add content_type
```

You can add a behavior with the following command.

```shell
make add behavior
```

```{seealso}
You can check the list of available subtemplates in the [`bobtemplates.plone` `README.md` file](https://github.com/plone/bobtemplates.plone/?tab=readme-ov-file#provided-subtemplates).
See also the documentation of [Mockup and Patternslib](https://6.docs.plone.org/classic-ui/mockup.html) for how to build the UI toolkit for Classic UI.
```

## License

The project is licensed under GPLv2.

## Credits and acknowledgements 🙏

Generated using [Cookieplone (1.0.0)](https://github.com/plone/cookieplone) and [cookieplone-templates (200cfed)](https://github.com/plone/cookieplone-templates/commit/200cfedd5380ee321abf39661a3ad4d83538ae66) on 2026-07-28 15:05:54.907737. A special thanks to all contributors and supporters!
