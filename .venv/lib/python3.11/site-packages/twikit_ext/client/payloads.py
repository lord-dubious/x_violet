from collections import defaultdict
from typing import Optional


class BasePayload:
    @classmethod
    def construct(cls):
        raise NotImplementedError


class FlowSubtaskPayload(BasePayload):
    pass


class FlowStartData(FlowSubtaskPayload):
    subtask_versions = {
        'action_list': 2,
        'alert_dialog': 1,
        'app_download_cta': 1,
        'check_logged_in_account': 1,
        'choice_selection': 3,
        'contacts_live_sync_permission_prompt': 0,
        'cta': 7,
        'email_verification': 2,
        'end_flow': 1,
        'enter_date': 1,
        'enter_email': 2,
        'enter_password': 5,
        'enter_phone': 2,
        'enter_recaptcha': 1,
        'enter_text': 5,
        'enter_username': 2,
        'generic_urt': 3,
        'in_app_notification': 1,
        'interest_picker': 3,
        'js_instrumentation': 1,
        'menu_dialog': 1,
        'notifications_permission_prompt': 2,
        'open_account': 2,
        'open_home_timeline': 1,
        'open_link': 1,
        'phone_verification': 4,
        'privacy_options': 1,
        'security_key': 3,
        'select_avatar': 4,
        'select_banner': 2,
        'settings_list': 7,
        'show_code': 1,
        'sign_up': 2,
        'sign_up_review': 4,
        'tweet_selection_urt': 1,
        'update_users': 1,
        'upload_media': 1,
        'user_recommendations_list': 4,
        'user_recommendations_urt': 1,
        'wait_spinner': 3,
        'web_modal': 1
    }

    @classmethod
    def construct(
        cls,
        location: str,
        requested_variant: Optional[str] = None
    ):
        input_flow_data = {
            'flow_context': {
                'debug_overrides': {},
                'start_location': {
                    'location': location
                }}}
        if requested_variant:
            input_flow_data["requested_variant"] = requested_variant

        return {
            'input_flow_data': input_flow_data,
            'subtask_versions': cls.subtask_versions}


class FlowLoginStartData(FlowStartData):
    @classmethod
    def construct(cls):
        return super().construct(location='splash_screen')


class LoginJsInstrumentationSubtask(FlowSubtaskPayload):
    @classmethod
    def construct(cls, ui_metrix: str):
        return {
            "subtask_id": "LoginJsInstrumentationSubtask",
            "js_instrumentation": {
                "response": ui_metrix,
                "link": "next_link"
            }}


class LoginEnterUserIdentifierSSO(FlowSubtaskPayload):
    @classmethod
    def construct(cls, auth_info: str):
        return {
            'subtask_id': 'LoginEnterUserIdentifierSSO',
            'settings_list': {
                'setting_responses': [
                    {
                        'key': 'user_identifier',
                        'response_data': {
                            'text_data': {'result': auth_info}
                        }
                    }
                ],
                'link': 'next_link'
            }}


class LoginEnterAlternateIdentifierSubtask(FlowSubtaskPayload):
    @classmethod
    def construct(cls, auth_info: str):
        return {
            'subtask_id': 'LoginEnterAlternateIdentifierSubtask',
            'enter_text': {
                'text': auth_info,
                'link': 'next_link'
            }}


class LoginEnterPassword(FlowSubtaskPayload):
    @classmethod
    def construct(cls, password: str):
        return {
            'subtask_id': 'LoginEnterPassword',
            'enter_password': {
                'password': password,
                'link': 'next_link'
            }}


class LoginAcid(FlowSubtaskPayload):
    @classmethod
    def construct(cls, code: str):
        return {
            'subtask_id': 'LoginAcid',
            'enter_text': {
                'text': code,
                'link': 'next_link'
            }}


class LoginTwoFactorAuthChallenge(FlowSubtaskPayload):
    @classmethod
    def construct(cls, totp_code: str):
        return {
            'subtask_id': 'LoginTwoFactorAuthChallenge',
            'enter_text': {
                'text': totp_code,
                'link': 'next_link'
            }}


class AccountDuplicationCheck(FlowSubtaskPayload):
    @classmethod
    def construct(cls):
        return {
            'subtask_id': 'AccountDuplicationCheck',
            'check_logged_in_account': {
                'link': 'AccountDuplicationCheck_false'
            }}


class TwoFactorUnenrollmentStartData(FlowStartData):
    @classmethod
    def construct(cls, requested_variant: str):
        return super().construct(
            location='settings',
            requested_variant=requested_variant)


class TwoFactorUnenrollmentVerifyPasswordSubtask(FlowSubtaskPayload):
    @classmethod
    def construct(cls, password: str):
        return {
            "subtask_id": "TwoFactorUnenrollmentVerifyPasswordSubtask",
            "enter_password": {
                "password": password,
                "link": "next_link"
            }}


class TwoFactorUnenrollmentSubtask(FlowSubtaskPayload):
    @classmethod
    def construct(cls):
        return {
            "subtask_id": "TwoFactorUnenrollmentSubtask",
            "cta": {
                "link": "next_link"
            }}


class TwoFactorAuthAppEnrollmentStartData(FlowStartData):
    @classmethod
    def construct(cls):
        return super().construct(location='settings')


class TwoFactorEnrollmentVerifyPasswordSubtask(FlowSubtaskPayload):
    @classmethod
    def construct(cls, password: str):
        return {
            "subtask_id": "TwoFactorEnrollmentVerifyPasswordSubtask",
            "enter_password": {
                "password": password,
                "link": "next_link"
            }}


class TwoFactorEnrollmentAuthenticationAppBeginSubtask(FlowSubtaskPayload):
    @classmethod
    def construct(cls):
        return {
            "subtask_id": "TwoFactorEnrollmentAuthenticationAppBeginSubtask",
            "action_list": {
                "link": "next_link"
            }}


class TwoFactorEnrollmentAuthenticationAppQrCodeSubtask(FlowSubtaskPayload):
    @classmethod
    def construct(cls):
        return {
            "subtask_id": "TwoFactorEnrollmentAuthenticationAppQrCodeSubtask",
            "show_code": {
                "link": "next_link"
            }}


class TwoFactorEnrollmentAuthenticationAppEnterCodeSubtask(FlowSubtaskPayload):
    @classmethod
    def construct(cls, code: str | int):
        return {
            "subtask_id": "TwoFactorEnrollmentAuthenticationAppEnterCodeSubtask",
            "enter_text": {
                "text": str(code),
                "link": "next_link"
            }}


class TwoFactorEnrollmentAuthenticationAppCompleteSubtask(FlowSubtaskPayload):
    @classmethod
    def construct(cls):
        return {
            "subtask_id": "TwoFactorEnrollmentAuthenticationAppCompleteSubtask",
            "cta": {
                "link": "deep_link"
            }}


class ChangePasswordPayload(BasePayload):
    @classmethod
    def construct(cls, current_password: str, new_password: str):
        return {
            "current_password": current_password,
            "password": new_password,
            "password_confirmation": new_password,
        }


class ConfirmOAuth2Payload(BasePayload):
    @classmethod
    def construct(cls, auth_code: str):
        return {
            "approval": "true",
            "code": auth_code,
        }
