"""Strict authority-identifier normalization shared by source-rich import profiles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit

_AUTHORITY_SCHEMES = frozenset({"gnd", "viaf", "wikidata"})
_EXTERNAL_ID_SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_AUTHORITY_LOCAL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]*$")
_GND_HOSTS = frozenset({"d-nb.info", "www.d-nb.info"})
_VIAF_HOSTS = frozenset({"viaf.org", "www.viaf.org"})
_WIKIDATA_HOSTS = frozenset({"wikidata.org", "www.wikidata.org"})
_GND_PATH_PATTERNS = (
    re.compile(r"^/gnd/(?P<identifier>[A-Za-z0-9][A-Za-z0-9._~-]*)/?$"),
    re.compile(r"^/(?P<identifier>[A-Za-z0-9][A-Za-z0-9._~-]*)/?$"),
)
_VIAF_PATH_PATTERNS = (re.compile(r"^/viaf/(?P<identifier>[A-Za-z0-9][A-Za-z0-9._~-]*)/?$"),)
_WIKIDATA_PATH_PATTERNS = (re.compile(r"^/entity/(?P<identifier>[A-Za-z0-9][A-Za-z0-9._~-]*)/?$"),)

NormalizedExternalIdentifier = tuple[str, str]


class AuthorityIdentifierError(ValueError):
    """Report one source-safe authority normalization failure."""


@dataclass(frozen=True, slots=True)
class _ParsedIdentifierValue:
    compact_value: str
    is_absolute_uri: bool
    authority_identifier: NormalizedExternalIdentifier | None


def normalize_external_identifier(
    identifier_type: str,
    value: str,
) -> NormalizedExternalIdentifier | None:
    """Normalize one typed ID without trusting URI substrings or lookalike hosts."""
    normalized_type = identifier_type.strip().lower().replace("-", "_")
    if not _EXTERNAL_ID_SCHEME_PATTERN.fullmatch(normalized_type):
        msg = "identifier type is invalid or unsupported"
        raise AuthorityIdentifierError(msg)

    parsed_value = _parse_identifier_value(value)
    uri_identifier = parsed_value.authority_identifier
    if normalized_type in _AUTHORITY_SCHEMES:
        if parsed_value.is_absolute_uri:
            if uri_identifier is None:
                msg = "declared authority requires a canonical authority URI"
                raise AuthorityIdentifierError(msg)
            if uri_identifier[0] != normalized_type:
                msg = "declared authority conflicts with the identifier URI"
                raise AuthorityIdentifierError(msg)
            return uri_identifier
        if not _AUTHORITY_LOCAL_ID_PATTERN.fullmatch(parsed_value.compact_value):
            msg = "authority-local identifier contains unsupported characters"
            raise AuthorityIdentifierError(msg)
        return normalized_type, parsed_value.compact_value

    if uri_identifier is not None:
        if normalized_type == "uri":
            return uri_identifier
        msg = "identifier type conflicts with the authority URI"
        raise AuthorityIdentifierError(msg)
    if normalized_type == "uri":
        return None
    return normalized_type, value


def add_external_identifier(
    identifiers: dict[str, str],
    *,
    identifier_type: str,
    value: str,
) -> None:
    """Add one normalized ID and reject duplicate normalized schemes."""
    normalized = normalize_external_identifier(identifier_type, value)
    if normalized is None:
        return
    scheme, normalized_value = normalized
    if scheme in identifiers:
        msg = "duplicate normalized identifier schemes"
        raise AuthorityIdentifierError(msg)
    identifiers[scheme] = normalized_value


def _parse_identifier_value(value: str) -> _ParsedIdentifierValue:
    compact_value = "".join(value.split())
    try:
        parsed = urlsplit(compact_value)
    except ValueError:
        return _ParsedIdentifierValue(
            compact_value=compact_value,
            is_absolute_uri=_looks_like_absolute_uri(compact_value),
            authority_identifier=None,
        )

    is_absolute_uri = bool(parsed.scheme)
    authority_identifier = _authority_identifier_from_uri(parsed) if is_absolute_uri else None
    return _ParsedIdentifierValue(
        compact_value=compact_value,
        is_absolute_uri=is_absolute_uri,
        authority_identifier=authority_identifier,
    )


def _authority_identifier_from_uri(
    parsed: SplitResult,
) -> NormalizedExternalIdentifier | None:
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
    ):
        return None

    hostname = (parsed.hostname or "").lower()
    if hostname in _GND_HOSTS:
        return _match_authority_path("gnd", parsed.path, _GND_PATH_PATTERNS)
    if hostname in _VIAF_HOSTS:
        return _match_authority_path("viaf", parsed.path, _VIAF_PATH_PATTERNS)
    if hostname in _WIKIDATA_HOSTS:
        return _match_authority_path("wikidata", parsed.path, _WIKIDATA_PATH_PATTERNS)
    return None


def _match_authority_path(
    scheme: str,
    path: str,
    patterns: tuple[re.Pattern[str], ...],
) -> NormalizedExternalIdentifier | None:
    for pattern in patterns:
        if match := pattern.fullmatch(path):
            return scheme, match.group("identifier")
    return None


def _looks_like_absolute_uri(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", value))
