from .utils import StrEnum


class AccountStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    BAD_TOKEN = "BAD_TOKEN"
    SUSPENDED = "SUSPENDED"
    LOCKED = "LOCKED"
    CONSENT_LOCKED = "CONSENT_LOCKED"
    GOOD = "GOOD"
    NOT_FOUND = "NOT_FOUND"
    BAD_PROXY = 'BAD_PROXY'
