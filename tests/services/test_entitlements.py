import pytest

from app.models.enums import MembershipTier
from app.services.entitlements import EntitlementService


def test_free_is_the_anonymous_default():
    assert EntitlementService.for_tier(None) == EntitlementService.for_tier(MembershipTier.FREE)


@pytest.mark.parametrize(
    ("tier", "static_map", "personalized_itinerary"),
    [
        (MembershipTier.FREE, False, False),
        (MembershipTier.LITE, True, False),
        (MembershipTier.PREMIUM, True, True),
    ],
)
def test_entitlement_matrix(tier, static_map, personalized_itinerary):
    entitlements = EntitlementService.for_tier(tier)

    assert entitlements.text_catalog is True
    assert entitlements.exports is True
    assert entitlements.static_map is static_map
    assert entitlements.personalized_itinerary is personalized_itinerary


def test_unknown_membership_tier_is_rejected():
    with pytest.raises(ValueError, match="Unsupported membership tier"):
        EntitlementService.for_tier("vip")
