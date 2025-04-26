from pydantic import BaseModel
from typing import List, Optional


class TwoFactorMethod(BaseModel):
    id: str
    userId: str
    twoFactorType: str
    createdAtMs: str
    lastUsedAtMs: Optional[str] = None
    purpose: str
    tags: Optional[List[str]] = None


class TwoFactorAuthConfig(BaseModel):
    twoFactorAuthEnabled: bool
    methods: List[TwoFactorMethod]
    isOldPushUser: bool
