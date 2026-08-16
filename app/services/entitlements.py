from dataclasses import dataclass

from app.models.enums import MembershipTier


@dataclass(frozen=True)
class Entitlements:
    text_catalog: bool
    exports: bool
    static_map: bool
    static_route: bool
    personalized_itinerary: bool


class EntitlementService:
    """The single source of truth for membership feature access."""

    _MATRIX = {
        MembershipTier.FREE: Entitlements(True, True, False, False, False),
        MembershipTier.LITE: Entitlements(True, True, True, True, False),
        MembershipTier.PREMIUM: Entitlements(True, True, True, True, True),
    }

    @classmethod
    def for_tier(cls, tier: MembershipTier | str | None) -> Entitlements:
        if tier is None:
            return cls._MATRIX[MembershipTier.FREE]
        try:
            normalized = MembershipTier(tier)
        except ValueError as exc:
            raise ValueError(f"Unsupported membership tier: {tier}") from exc
        return cls._MATRIX[normalized]
