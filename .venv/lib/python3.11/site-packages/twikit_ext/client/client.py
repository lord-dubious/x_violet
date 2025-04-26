from typing import Optional, Union, Dict, Any, Tuple, List, Literal
from time import time
import asyncio
from http.cookiejar import Cookie

from loguru import logger
from twikit import Client as OriginalClient, Capsolver, User
from twikit.client.gql import GQLClient
from twikit.x_client_transaction import ClientTransaction
from twikit.constants import TOKEN, DOMAIN
from twikit.errors import (
    Unauthorized, TwitterException, NotFound, Forbidden, TooManyRequests, BadRequest,
    UserNotFound, AccountSuspended, AccountLocked)
from twikit.utils import Flow, find_dict
import pyotp
from proxystr import Proxy, AsyncClient
import httpx
from python_socks._errors import ProxyConnectionError

from ..models import Profile
from ..enums import AccountStatus
from .models import EditProfileData, OAuth2Params
from .v11 import V11Client, Endpoint
from .responses import (
    TwoFactorAuthConfig, TwoFactorMethod)
from . import payloads as pl


class Client(OriginalClient):
    """
    The Сlient always updates Profile attributes if they have been changed.
    Therefore, it is recommended to save the Profile after closing the Client.

    Example
    -------
    try:
        async with Client({'auth_token': '123sdf'}) as client:
            client.connect()
            ...
    finally:
        client.profile.save('profile.json')
    -------

    Usefull methods:
    ---------------
    Client.connect()
    Client.change_username()
    Client.change_password()
    """

    def __init__(
        self,
        profile: Profile | Dict,
        *,
        proxy: Union[Proxy, str] = None,  # also can be added as Profile attr
        capsolver_api_key: str = None,
        wait_on_rate_limit: bool = True,
        language: str = 'en-US',
        user_agent: str = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        **httpx_session_kwargs
    ):
        self.profile = profile if isinstance(profile, Profile) else Profile(**profile)
        self.me: User = None

        if self.profile.proxy:
            self._proxy = self.profile.proxy
        elif proxy:
            self._proxy = Proxy(proxy)
        else:
            self._proxy = None

        self.http = AsyncClient(proxy=self._proxy, **httpx_session_kwargs)
        self.language = language
        self.wait_on_rate_limit = wait_on_rate_limit

        if capsolver_api_key:
            self.captcha_solver = Capsolver(api_key=capsolver_api_key)
            self.captcha_solver.client = self
        else:
            self.captcha_solver = None

        self.client_transaction = ClientTransaction()

        self._token = TOKEN
        self._user_id = self.profile.user_id
        self._user_agent = user_agent
        self._act_as = None

        self.gql = GQLClient(self)
        self.v11 = V11Client(self)

    async def connect(self) -> User:
        self.profile.status = AccountStatus.UNKNOWN
        if self.profile.auth_token:
            self._set_profile_auth_token()
            try:
                try:
                    return await self.user()
                except (NotFound, Forbidden):
                    logger.warning('NotFound')
                    return await self.user()
            except Unauthorized:
                pass

        await self.login()
        return await self.user()

    async def login(self):
        await self._login(
            auth_info_1=self.profile.auth_info_1,
            auth_info_2=self.profile.auth_info_2,
            password=self.profile._password,
            totp_secret=self.profile.totp_secret)
        self.profile.auth_token = self.http.cookies.get('auth_token')

    async def user(self) -> User:
        self.me = await super().user()
        self.profile.username = self.me.name
        self.profile.user_id = self.me.id
        self.profile.status = AccountStatus.GOOD
        return self.me

    async def change_username(self, new_username: str) -> bool:
        payload = {"screen_name": new_username}
        data, response = await self.post(Endpoint.SETTINGS, data=payload, headers=self._base_headers)
        self.profile.username = data["screen_name"]
        return self.profile.username == new_username

    async def change_name(self, name: str) -> bool:
        """Max length = 50 symbols, Min length = 1"""
        data = await self._update_profile(EditProfileData(name=name))
        return data.name == name

    async def change_bio(self, description: str) -> bool:
        """Max length = 160 symbols, can be an empty string '' """
        data = await self._update_profile(EditProfileData(description=description))
        return data.description == description

    async def change_location(self, location: str) -> bool:
        """Max length = 30 symbols, can be an empty string '' """
        data = await self._update_profile(EditProfileData(location=location))
        return data.location == location

    async def change_password(self, new_password: str) -> bool:
        """После изменения пароля обновляется auth_token!"""
        if not self.profile.password:
            raise TwitterException(f"Specify the current password before changing it")

        payload = pl.ChangePasswordPayload.construct(self.profile.password, new_password)
        data, response = await self.post(Endpoint.CHANGE_PASSWORD, data=payload, headers=self._base_headers)
        if data["status"] == "ok":
            self.profile.password = new_password
            return True

    async def get_enabled_two_factor_methods(self) -> List[TwoFactorMethod]:
        url = Endpoint.twoFactorAuthSettings2.format(self.profile.user_id)
        data, response = await self.get(url, headers=self._base_headers)
        enabled_methods = TwoFactorAuthConfig(**data).methods
        method_types = [m.twoFactorType for m in enabled_methods]
        if 'BackupCode' not in method_types:
            self.profile.backup_code = None
        if 'Totp' not in method_types:
            self.profile.totp_secret = None
        return enabled_methods

    async def is_totp_enabled(self) -> bool:
        return await self._is_two_factor_method_enabled(method_type='Totp')

    async def disable_totp(self) -> bool:
        if await self._disable_two_factor_method(method='authenticationApp'):
            return not await self.is_totp_enabled()

    async def enable_totp(self) -> bool:
        if await self._enable_two_factor_auth_app_method():
            if await self.is_totp_enabled():
                await self.get_backup_code()
                return True

    async def is_backup_code_enabled(self):
        return await self._is_two_factor_method_enabled(method_type='BackupCode')

    async def get_backup_code(self) -> str:
        data, response = await self.get(Endpoint.BACKUP_CODE, headers=self._base_headers)
        self.profile.backup_code = data["codes"][0]
        return self.profile.backup_code

    async def change_backup_code(self) -> str:
        data, response = await self.post(Endpoint.BACKUP_CODE, data={}, headers=self._base_headers)
        self.profile.backup_code = data["codes"][0]
        return self.profile.backup_code

    async def update_profile_avatar(self):
        # TODO
        raise NotImplementedError

    async def update_profile_banner(self):
        # TODO
        raise NotImplementedError

    async def oauth2(self, params: OAuth2Params | Dict | str) -> str:
        """
        params can be just an auth url.
        returns the redirect_uri that contains state and code
        """
        if isinstance(params, str):
            params = OAuth2Params.from_url(params)
        elif isinstance(params, dict):
            params = OAuth2Params(**params)
        elif not isinstance(params, OAuth2Params):
            raise ValueError('Unsupported params format')
        return await self._oauth2(params=params)

    async def _oauth2(self, params: OAuth2Params) -> str:
        data, response = await self.get(Endpoint.OAUTH2, params=params.model_dump(), headers=self._base_headers)
        payload = pl.ConfirmOAuth2Payload.construct(data['auth_code'])
        data, response = await self.post(Endpoint.OAUTH2, data=payload, headers=self._base_headers)
        return data['redirect_uri']

    async def oauth(self):
        # TODO
        raise NotImplementedError

    def get_cookies(self) -> List[Dict]:
        """returns a copy of cookies"""
        cookies = []
        for cookie in self.http.cookies.jar:
            c = cookie.__dict__.copy()
            c['rest'] = c.pop('_rest')
            cookies.append(c)
        return cookies

    def set_cookies(self, cookies: List[Dict] | Dict, clear_cookies: bool = False) -> None:
        if clear_cookies:
            self.http.cookies.clear()

        if isinstance(cookies, dict):
            for name, value in cookies.items():
                self.http.cookies.set(name, value, domain=f'.{DOMAIN}', path='/')
        elif isinstance(cookies, (list, tuple)):
            for cookie_dict in cookies:
                self.http.cookies.jar.set_cookie(Cookie(**cookie_dict))
        else:
            raise ValueError('Unsupported cookies format')

    async def get_code_from_email(self):
        # TODO
        return

    async def request(self, *args, **kwargs) -> Tuple[Dict | Any, httpx.Response]:
        try:
            r = await super().request(*args, **kwargs)
        except Unauthorized:
            self.profile.status = AccountStatus.BAD_TOKEN
            raise
        except BadRequest as er:
            if '"code":399' in str(er):
                self.profile.status = AccountStatus.NOT_FOUND
                raise UserNotFound(str(er), headers=er.headers)
            raise
        except AccountSuspended:
            self.profile.status = AccountStatus.SUSPENDED
            raise
        except AccountLocked:
            self.profile.status = AccountStatus.LOCKED
            raise
        except TooManyRequests as er:
            print(er.rate_limit_reset)
            if self.wait_on_rate_limit and er.rate_limit_reset:
                sleep_time = int(er.rate_limit_reset) - int(time()) + 1

                if sleep_time > 0:
                    logger.warning(f"{self} --> Rate limited! Sleep time: {sleep_time} sec.")
                    await asyncio.sleep(sleep_time)
                return await self.request(*args, **kwargs)
            raise
        except (httpx.HTTPError, ProxyConnectionError, asyncio.TimeoutError):
            self.profile.status = AccountStatus.BAD_PROXY
            raise

        if auth_token := self.http.cookies.get('auth_token'):
            self.profile.auth_token = auth_token
        if ct0 := self.http.cookies.get('ct0'):
            self.profile.ct0 = ct0
        return r

    async def unlock(self):
        try:
            super().unlock()
        except Exception:
            self.profile.status = AccountStatus.LOCKED
            raise

    async def _update_profile(self, data: EditProfileData | Dict) -> EditProfileData:
        if isinstance(data, dict):
            data = EditProfileData(**data)
        data, response = await self.post(Endpoint.UPDATE_PROFILE, data=data.payload, headers=self._base_headers)
        await self.me.update()
        return EditProfileData(**data)

    async def _enable_two_factor_auth_app_method(self) -> bool:
        """It's recommended to use Client._is_two_factor_method_enabled() after executing this function"""
        if not self.profile.password:
            raise TwitterException(f"Specify the current password to use this function")

        flow = Flow(self, None)

        await flow.execute_task(
            params={'flow_name': 'two-factor-auth-app-enrollment'},
            data=pl.TwoFactorAuthAppEnrollmentStartData.construct())

        if flow.task_id == 'TwoFactorEnrollmentVerifyPasswordSubtask':
            await flow.execute_task(pl.TwoFactorEnrollmentVerifyPasswordSubtask.construct(self.profile.password))

        if flow.task_id == 'TwoFactorEnrollmentAuthenticationAppBeginSubtask':
            await flow.execute_task(pl.TwoFactorEnrollmentAuthenticationAppBeginSubtask.construct())

        for subtask in flow.response['subtasks']:
            if subtask['subtask_id'] == 'TwoFactorEnrollmentAuthenticationAppPlainCodeSubtask':
                self.profile.totp_secret = subtask['show_code']['code']
                totp_code = pyotp.TOTP(self.profile.totp_secret).now()

                await flow.execute_task(
                    pl.TwoFactorEnrollmentAuthenticationAppQrCodeSubtask.construct(),
                    pl.TwoFactorEnrollmentAuthenticationAppEnterCodeSubtask.construct(totp_code)
                )

        subtask_ids = [s['subtask_id'] for s in flow.response['subtasks']]
        if 'TwoFactorEnrollmentAuthenticationAppCompleteSubtask' in subtask_ids:
            await flow.execute_task(pl.TwoFactorEnrollmentAuthenticationAppCompleteSubtask.construct())

        if flow.response['subtasks']:
            raise TwitterException(str(flow.response['subtasks']))
        return flow.response.get('status') == 'success'

    async def _disable_two_factor_method(self, method: Literal['authenticationApp'] = 'authenticationApp') -> bool:
        """It's recommended to use Client._is_two_factor_method_enabled() after executing this function"""
        if not self.profile.password:
            raise TwitterException(f"Specify the current password to use this function")

        flow = Flow(self, None)

        await flow.execute_task(
            params={'flow_name': 'two-factor-unenrollment'},
            data=pl.TwoFactorUnenrollmentStartData.construct(f'{{"method":"{method}"}}'))

        if flow.task_id == 'TwoFactorUnenrollmentVerifyPasswordSubtask':
            await flow.execute_task(pl.TwoFactorUnenrollmentVerifyPasswordSubtask.construct(self.profile.password))

        if flow.task_id == 'TwoFactorUnenrollmentSubtask':
            await flow.execute_task(pl.TwoFactorUnenrollmentSubtask.construct())

        if flow.response['subtasks']:
            raise TwitterException(str(flow.response['subtasks']))
        return flow.response.get('status') == 'success'

    async def _is_two_factor_method_enabled(self, method_type: Literal['Totp', 'BackupCode']) -> bool:
        enabled_methods = await self.get_enabled_two_factor_methods()
        return method_type in [m.twoFactorType for m in enabled_methods]

    async def _login(
        self,
        *,
        auth_info_1: str,
        auth_info_2: str | None = None,
        password: str,
        totp_secret: str | None = None
    ) -> Optional[dict]:
        self.http.cookies.clear()
        guest_token = await self._get_guest_token()

        flow = Flow(self, guest_token)

        await flow.execute_task(params={'flow_name': 'login'}, data=pl.FlowLoginStartData.construct())
        await flow.sso_init('apple')
        await flow.execute_task(pl.LoginJsInstrumentationSubtask.construct(await self._ui_metrics()))

        await flow.execute_task(pl.LoginEnterUserIdentifierSSO.construct(auth_info_1))

        if flow.task_id == 'LoginEnterAlternateIdentifierSubtask':
            await flow.execute_task(pl.LoginEnterAlternateIdentifierSubtask.construct(auth_info_2))

        if flow.task_id == 'DenyLoginSubtask':
            raise TwitterException(flow.response['subtasks'][0]['cta']['secondary_text']['text'])

        await flow.execute_task(pl.LoginEnterPassword.construct(password))

        if flow.task_id == 'DenyLoginSubtask':
            raise TwitterException(flow.response['subtasks'][0]['cta']['secondary_text']['text'])

        if flow.task_id == 'LoginAcid':
            if code := await self.get_code_from_email():
                await flow.execute_task(pl.LoginAcid.construct(code))
            else:
                raise TwitterException(find_dict(flow.response, 'secondary_text', find_one=True)[0]['text'])

        if flow.task_id == 'LoginTwoFactorAuthChallenge':
            if totp_secret is None:
                raise TwitterException(find_dict(flow.response, 'secondary_text', find_one=True)[0]['text'])
            totp_code = pyotp.TOTP(totp_secret).now()
            await flow.execute_task(pl.LoginTwoFactorAuthChallenge.construct(totp_code))
        else:
            await flow.execute_task(pl.AccountDuplicationCheck.construct())

        if flow.response['subtasks'] and flow.task_id != 'LoginSuccessSubtask':
            raise TwitterException(str(flow.response['subtasks']))

    @property
    def _base_headers(self) -> Dict[str, str]:
        """переопределение оригинального метода.
        Попытка исправить выстрел в ногу автором оригинальной либы.
        Нужно убрать к херам "content-type" из _base_headers"""

        headers = super()._base_headers
        headers['Accept-Language'] = f'{self.language},{self.language.split("-")[0]};q=0.9'
        headers['X-Twitter-Client-Language'] = self.language.split("-")[0]
        if 'content-type' in headers:
            del headers['content-type']
        return headers

    def _set_profile_auth_token(self):
        cookies = {'auth_token': self.profile.auth_token}
        if self.profile.ct0:
            cookies['ct0'] = self.profile.ct0
        self.set_cookies(cookies=cookies)

    def _remove_duplicate_ct0_cookie(self):
        """В оригинальной либе нахуеверчено что-то с куками через жопу.
        Похоже сломаны штатные механизмы присвоение куков, из-за чего создаются дубликаты, которые надо удалять.
        Пришлось переопределить get_cookies() и set_cookies() чтоб исправить эту дичь"""
        return

    def __str__(self):
        return f"{self.__class__.__name__}({self.profile.username})"

    def __repr__(self):
        return self.__str__()

    async def close(self):
        await self.http.aclose()

    async def __aenter__(self) -> 'Client':
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()
