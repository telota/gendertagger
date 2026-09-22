"""Public deployment-branding contracts (ADR-0036).

Every field describes operator-supplied configuration, never frontend source code: an unconfigured
value is absent rather than filled with a default institutional identity. See
`AppSettings.branding` for how these values are populated.
"""

from pydantic import BaseModel, ConfigDict, Field


class BrandingInitiative(BaseModel):
    """One named institutional context the deployment is developed within.

    The name is a proper name and is rendered untranslated by the client.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    url: str = Field(min_length=1)


class BrandingLegalEntity(BaseModel):
    """Provider details for the client's legal notice, modelled on a BBAW-style imprint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    legal_form: str | None = None
    address_lines: list[str] = Field(default_factory=list)
    telephone: str | None = None
    telephone_href: str | None = None
    representative: str | None = None
    vat_id: str | None = None


class BrandingInfo(BaseModel):
    """Deployment branding as the browser client receives it from `GET /api/v1/branding`.

    An operator who has not configured a field sees it as `None` here; the client renders that as an
    explicit "not configured" state rather than inventing a value.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    institution_name: str | None = None
    institution_url: str | None = None
    logo_url: str | None = Field(
        default=None,
        description="Same-origin path to GET, e.g. '/api/v1/branding/logo'; absent when no logo is configured.",
    )
    editors: list[str] = Field(default_factory=list)
    published_since_year: int | None = None
    initiatives: list[BrandingInitiative] = Field(default_factory=list)
    contact_email: str | None = None
    privacy_notice_url: str | None = None
    legal_entity: BrandingLegalEntity | None = None
