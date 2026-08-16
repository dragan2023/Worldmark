from enum import StrEnum


class MembershipTier(StrEnum):
    FREE = "free"
    LITE = "lite"
    PREMIUM = "premium"


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
