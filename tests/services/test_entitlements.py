import pytest

from app.models.enums import MembershipTier
from app.services.entitlements import EntitlementService


def test_free_is_the_anonymous_default():
    assert EntitlementService.for_tier(None) == EntitlementService.for_tier(MembershipTier.FREE)


@pytest.mark.parametrize("tier", [MembershipTier.FREE, MembershipTier.LITE, MembershipTier.PREMIUM])
def test_all_tiers_have_full_access(tier):
    entitlements = EntitlementService.for_tier(tier)

    assert entitlements.text_catalog is True
    assert entitlements.exports is True
    assert entitlements.static_map is True
    assert entitlements.static_route is True
    assert entitlements.personalized_itinerary is True


def test_unknown_membership_tier_is_rejected():
    with pytest.raises(ValueError, match="Unsupported membership tier"):
        EntitlementService.for_tier("vip")
