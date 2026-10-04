"""Bounded detailed diagnostics for authorized persisted operational failures."""

import re

_MAX_DIAGNOSTIC_LENGTH = 500
_URL_CREDENTIALS = re.compile(r"([a-z][a-z0-9+.-]*://)([^/@\s]+@)", flags=re.IGNORECASE)


def sanitized_diagnostic(error: BaseException) -> str:
    """Redact URL user information before bounding a detailed failure diagnostic.

    This formatter is for authorized operational resources, not anonymous
    responses or snapshot-import public messages. It does not claim to remove
    arbitrary secrets or editorial content from an exception's text.
    """
    text = f"{type(error).__name__}: {error}".strip()
    text = _URL_CREDENTIALS.sub(r"\1<redacted>@", text)
    if len(text) > _MAX_DIAGNOSTIC_LENGTH:
        return text[: _MAX_DIAGNOSTIC_LENGTH - 1] + "…"
    return text
