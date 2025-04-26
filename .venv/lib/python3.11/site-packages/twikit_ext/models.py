from typing import Optional
import json

from pydantic import BaseModel
from proxystr import Proxy

from .enums import AccountStatus


class EmailProfile(BaseModel):
    """Not implemented"""
    email: str
    password: str
    totp_secret: Optional[str] = None


class Profile(BaseModel, validate_assignment=True):
    auth_token: Optional[str] = None
    ct0: Optional[str] = None
    proxy: Optional[Proxy] = None

    username: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    password: Optional[str] = None
    totp_secret: Optional[str] = None
    backup_code: Optional[str] = None

    user_id: Optional[str] = None
    status: AccountStatus = AccountStatus.UNKNOWN

    email_profile: Optional[EmailProfile] = None  # Not implemented

    @property
    def auth_info_1(self):
        info = self.all_auth_info
        if len(info) > 0:
            return self.all_auth_info[0]
        raise ValueError('No auth info provided')

    @property
    def auth_info_2(self):
        info = self.all_auth_info
        if len(info) > 1:
            return self.all_auth_info[1]

    @property
    def _password(self):
        if self.password:
            return self.password
        raise ValueError("No password provided")

    @property
    def all_auth_info(self):
        info = (self.email, self.phone, self.username)
        return [i for i in info if i]

    def save(self, filepath: str) -> None:
        with open(filepath, 'w', encoding='utf-8') as file:
            file.write(self.model_dump_json(exclude_none=True, indent=4))

    @classmethod
    def load(cls, filepath: str) -> 'Profile':
        with open(filepath, encoding='utf-8') as file:
            return cls(**json.load(file))
