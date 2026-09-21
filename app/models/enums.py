from enum import StrEnum


class MembershipTier(StrEnum):
    FREE = "free"
    LITE = "lite"
    PREMIUM = "premium"


class UserRole(StrEnum):
    """权限角色（与付费 MembershipTier 相互独立）。"""

    ADMIN = "admin"
    LEVEL1 = "level1"
    LEVEL2 = "level2"


class UserStatus(StrEnum):
    ACTIVE = "active"
    BANNED = "banned"


class IPType(StrEnum):
    LITERATURE = "literature"
    GAME = "game"
    SCREEN = "screen"


class VerificationStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    REJECTED = "rejected"


class PublicationStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ItineraryStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
