from typing import Optional
from urllib.parse import urlparse, parse_qs

from pydantic import BaseModel, Field


class EditProfileData(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    description: Optional[str] = Field(default=None, max_length=160)
    location: Optional[str] = Field(default=None, max_length=30)

    @property
    def payload(self):
        return self.model_dump(exclude_none=True)


class OAuth2Params(BaseModel):
    client_id: str
    state: str
    redirect_uri: str
    code_challenge: Optional[str] = None
    code_challenge_method: Optional[str] = None
    scope: str
    response_type: str

    @classmethod
    def from_url(cls, url: str) -> 'OAuth2Params':
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        query_params = {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}
        return cls(**query_params)
