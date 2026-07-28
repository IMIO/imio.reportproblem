"""Audit logging of problem reports, through ``collective.fingerpointing``.

``collective.fingerpointing`` is an optional dependency, pulled in by the
``audit`` extra.  The subscriber below is registered from
``fingerpointing.zcml``, which ``configure.zcml`` includes only when the
package is installed: its mere presence turns audit logging on, there is no
setting to flip.  Unlike the captcha, no security trade-off hangs on that
choice.

The module stays importable without the dependency, so that the test suite --
or anything else poking at it -- does not blow up.
"""

from imio.reportproblem import logger


try:
    from collective.fingerpointing.config import AUDIT_MESSAGE
    from collective.fingerpointing.logger import log_info
    from collective.fingerpointing.utils import get_request_information

    HAS_FINGERPOINTING = True
except ImportError:  # pragma: no cover
    HAS_FINGERPOINTING = False


#: ``action`` field written to the audit log.
AUDIT_ACTION = "report_problem"

#: The only keys read out of the report payload.  See ``_payload_metadata``.
SAFE_PAYLOAD_KEYS = ("reason", "userid")

#: Keys the payload also holds, holding personal data about the reporter.
#: They must never reach the audit log.
PERSONAL_PAYLOAD_KEYS = ("name", "email", "message")


def _scrub(value):
    """Return ``value`` as a single-line string, fit for a log record.

    Collapsing whitespace keeps one report to one log line, whatever ends up
    in the reason token.
    """
    return " ".join(str(value).split()) if value else "-"


def _content_metadata(obj):
    """Return the identifying metadata of the reported content.

    Nothing here says anything about the reporter: it is the content's own
    UID, path and portal type.
    """
    uid = getattr(obj, "UID", None)
    get_physical_path = getattr(obj, "getPhysicalPath", None)
    return {
        "uid": _scrub(uid() if callable(uid) else None),
        "path": _scrub("/".join(get_physical_path()) if get_physical_path else None),
        "portal_type": _scrub(getattr(obj, "portal_type", None)),
    }


def _payload_metadata(data):
    """Pick the non-personal bits out of the report payload.

    Two keys are read, and two only: ``userid``, reduced to a boolean telling
    whether the report was authenticated, and ``reason``, the reason token.

    The payload handed to the event also holds the reporter's name, email
    address and message, under ``name``, ``email`` and ``message``.  Those are
    personal data and never leave this function -- see ``log_problem_reported``
    for why.  The mapping is therefore read key by key, and never dumped whole.
    """
    return {
        "authenticated": bool(data.get("userid")),
        # Kept last: a reason token may hold a space, and a trailing field
        # cannot then swallow the key that would follow it.
        "reason": _scrub(data.get("reason")),
    }


def build_audit_extras(obj, data):
    """Return the ``extras`` field of the audit log line for a report.

    Only metadata goes in: the content's UID and path, its portal type, the
    reason token and whether the report was authenticated.
    """
    metadata = _content_metadata(obj)
    metadata.update(_payload_metadata(data or {}))
    return " ".join(f"{key}={value}" for key, value in metadata.items())


def log_problem_reported(event):
    """Write a problem report to the audit log -- metadata only.

    The audit log is a long-retention file.  Copying a citizen's name, email
    address or message into it would build an unmanaged parallel database of
    personal data, so the line holds no personal data about the reporter at
    all: only the content's UID and path, its portal type, the reason token,
    and whether the report was authenticated.

    ``collective.fingerpointing`` prepends the acting user and the IP address
    itself, as it does for every other action it logs.
    """
    if not HAS_FINGERPOINTING:  # pragma: no cover
        logger.warning(
            "collective.fingerpointing is not importable: the problem report "
            "was not written to the audit log."
        )
        return

    user, ip = get_request_information()
    extras = build_audit_extras(event.object, event.data)
    log_info(AUDIT_MESSAGE.format(user, ip, AUDIT_ACTION, extras))
