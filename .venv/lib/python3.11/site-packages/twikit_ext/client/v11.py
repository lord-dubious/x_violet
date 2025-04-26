from twikit.constants import DOMAIN, TOKEN
from twikit.client.v11 import Endpoint, V11Client as OriginalClient


Endpoint.CHANGE_PASSWORD = f'https://{DOMAIN}/i/api/i/account/change_password.json'
Endpoint.twoFactorAuthSettings2 = f"https://{DOMAIN}/i/api/1.1/strato/column/User/{{}}/account-security/twoFactorAuthSettings2"
Endpoint.BACKUP_CODE = f"https://api.{DOMAIN}/1.1/account/backup_code.json"
Endpoint.UPDATE_PROFILE = f"https://api.{DOMAIN}/1.1/account/update_profile.json"
Endpoint.OAUTH2 = f"https://{DOMAIN}/i/api/2/oauth2/authorize"


class V11Client(OriginalClient):
    async def onboarding_task(self, guest_token, token, subtask_inputs, data=None, **kwargs):
        if data is None:
            data = {}
        if token is not None:
            data['flow_token'] = token
        if subtask_inputs is not None:
            data['subtask_inputs'] = subtask_inputs

        if guest_token is None:
            headers = self.base._base_headers
        else:
            headers = {
                'x-guest-token': guest_token,
                'Authorization': f'Bearer {TOKEN}'
            }

            if self.base._get_csrf_token():
                headers["x-csrf-token"] = self.base._get_csrf_token()
                headers["x-twitter-auth-type"] = "OAuth2Session"

        return await self.base.post(
            Endpoint.ONBOARDING_TASK,
            json=data,
            headers=headers,
            **kwargs
        )
