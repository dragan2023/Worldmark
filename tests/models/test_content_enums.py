from app.models.enums import IPType, MembershipTier, PublicationStatus, VerificationStatus


def test_domain_enums_have_only_planned_values():
    assert {member.value for member in IPType} == {"literature", "game", "screen"}
    assert {member.value for member in MembershipTier} == {"free", "lite", "premium"}
    assert {member.value for member in VerificationStatus} == {"candidate", "verified", "rejected"}
    assert {member.value for member in PublicationStatus} == {"draft", "published", "archived"}
