"""Synchronous CSG API client.

This module intentionally remains synchronous because CSG updates are infrequent
and each update only requires a handful of HTTP requests. Home Assistant will run
the blocking calls via ``async_add_executor_job``.
"""

from __future__ import annotations

import datetime
import json
import logging
import random
import time
from base64 import b64decode, b64encode
from copy import copy
from hashlib import md5
from typing import Any

import requests
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA

from .const import (
    AREACODE_FALLBACK,
    ATTR_ACCOUNT_NUMBER,
    ATTR_ADDRESS,
    ATTR_AREA_CODE,
    ATTR_AUTH_TOKEN,
    ATTR_ELE_CUSTOMER_ID,
    ATTR_METERING_POINT_ID,
    ATTR_METERING_POINT_NUMBER,
    ATTR_USER_NAME,
    BASE_PATH_APP,
    BASE_PATH_WEB,
    CREDENTIAL_PUBKEY,
    HEADER_CUST_NUMBER,
    HEADER_X_AUTH_TOKEN,
    JSON_KEY_ACCT_ID,
    JSON_KEY_AREA_CODE,
    JSON_KEY_CRED_TYPE,
    JSON_KEY_CUST_NUMBER,
    JSON_KEY_DATA,
    JSON_KEY_ELE_CUST_ID,
    JSON_KEY_LOGON_CHAN,
    JSON_KEY_MESSAGE,
    JSON_KEY_METERING_POINT_ID,
    JSON_KEY_METERING_POINT_NUMBER,
    JSON_KEY_PARAM,
    JSON_KEY_SMS_CODE,
    JSON_KEY_STA,
    JSON_KEY_YEAR_MONTH,
    LOGIN_TYPE_PHONE_CODE,
    LOGIN_TYPE_PHONE_PWD_CODE,
    LOGIN_TYPE_TO_QR_APP_NAME,
    LOGIN_TYPE_TO_QR_CODE_TYPE,
    LoginType,
    LOGON_CHANNEL_HANDHELD_HALL,
    PARAM_IV,
    PARAM_KEY,
    QRCodeType,
    REQUEST_TIMEOUT,
    RESP_STA_LOGIN_WRONG_CREDENTIAL,
    RESP_STA_NO_LOGIN,
    RESP_STA_QR_NOT_SCANNED,
    RESP_STA_SUCCESS,
    SEND_MSG_TYPE_VERIFICATION_CODE,
    VERIFICATION_CODE_TYPE_LOGIN,
)
from .exceptions import (
    CSGAPIError,
    CSGHTTPError,
    InvalidCredentials,
    NotLoggedIn,
    QrCodeExpired,
)

# Public re-exports of the API package
__all__ = [
    "CSGClient",
    "CSGElectricityAccount",
    "CSGAPIError",
    "CSGHTTPError",
    "InvalidCredentials",
    "NotLoggedIn",
    "QrCodeExpired",
    "LoginType",
    "QRCodeType",
    "LOGIN_TYPE_TO_QR_APP_NAME",
    "LOGIN_TYPE_TO_QR_CODE_TYPE",
    "generate_qr_login_id",
    "encrypt_credential",
    "encrypt_params",
    "decrypt_params",
    "safe_float",
]

_LOGGER = logging.getLogger(__name__)


def generate_qr_login_id() -> str:
    """Generate a unique id for QR login (mirrors JS implementation)."""
    rand_str = f"{int(time.time() * 1000)}{random.random()}"
    return md5(rand_str.encode()).hexdigest()


def encrypt_credential(password: str) -> str:
    """Encrypt password with RSA public key."""
    rsa_key = RSA.import_key(b64decode(CREDENTIAL_PUBKEY))
    cipher = PKCS1_v1_5.new(rsa_key)
    encrypted = cipher.encrypt(password.encode("utf8"))
    return b64encode(encrypted).decode()


def encrypt_params(params: dict[str, Any]) -> str:
    """Encrypt request body using AES-CBC."""
    json_cipher = AES.new(PARAM_KEY, AES.MODE_CBC, PARAM_IV)

    json_str = json.dumps(params, ensure_ascii=False, separators=(",", ":"))
    raw = json_str.encode("utf8")
    # Padding must be computed on the ENCODED byte length, not the character
    # count: Chinese characters take 3 bytes in UTF-8, so a character-based
    # pad produces a non-block-aligned payload and AES-CBC raises
    # "Data must be padded to 16 byte boundary".
    padded = raw + (16 - len(raw) % 16) * b"\x00"
    encrypted = json_cipher.encrypt(padded)
    return b64encode(encrypted).decode()


def decrypt_params(encrypted: str) -> dict[str, Any]:
    """Decrypt response body using AES-CBC."""
    json_cipher = AES.new(PARAM_KEY, AES.MODE_CBC, PARAM_IV)
    decrypted = json_cipher.decrypt(b64decode(encrypted))
    return json.loads(decrypted.decode().strip("\x00"))


def safe_float(value: Any, default: float | None = None) -> float | None:
    """Convert a value to float, returning default when not convertible."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class CSGElectricityAccount:
    """Represents one electricity billing account."""

    def __init__(
        self,
        account_number: str | None = None,
        area_code: str | None = None,
        ele_customer_id: str | None = None,
        metering_point_id: str | None = None,
        metering_point_number: str | None = None,
        address: str | None = None,
        user_name: str | None = None,
    ) -> None:
        self.account_number = account_number
        self.area_code = area_code
        self.ele_customer_id = ele_customer_id
        self.metering_point_id = metering_point_id
        self.metering_point_number = metering_point_number
        self.address = address
        self.user_name = user_name

    def dump(self) -> dict[str, str | None]:
        """Serialize the account to a dictionary."""
        return {
            ATTR_ACCOUNT_NUMBER: self.account_number,
            ATTR_AREA_CODE: self.area_code,
            ATTR_ELE_CUSTOMER_ID: self.ele_customer_id,
            ATTR_METERING_POINT_ID: self.metering_point_id,
            ATTR_METERING_POINT_NUMBER: self.metering_point_number,
            ATTR_ADDRESS: self.address,
            ATTR_USER_NAME: self.user_name,
        }

    @staticmethod
    def load(data: dict[str, Any]) -> CSGElectricityAccount:
        """Deserialize an account from a dictionary."""
        for key in (
            ATTR_ACCOUNT_NUMBER,
            ATTR_AREA_CODE,
            ATTR_ELE_CUSTOMER_ID,
            ATTR_METERING_POINT_ID,
            ATTR_ADDRESS,
            ATTR_USER_NAME,
        ):
            if key not in data:
                raise ValueError(f"Missing key {key}")
        return CSGElectricityAccount(
            account_number=data[ATTR_ACCOUNT_NUMBER],
            area_code=data[ATTR_AREA_CODE],
            ele_customer_id=data[ATTR_ELE_CUSTOMER_ID],
            metering_point_id=data[ATTR_METERING_POINT_ID],
            metering_point_number=data.get(ATTR_METERING_POINT_NUMBER),
            address=data[ATTR_ADDRESS],
            user_name=data[ATTR_USER_NAME],
        )


class CSGClient:
    """Implementation of CSG's mobile app API."""

    def __init__(self, auth_token: str | None = None) -> None:
        self._session: requests.Session = requests.Session()
        self._common_headers = {
            "Host": "95598.csg.cn",
            "Content-Type": "application/json;charset=utf-8",
            "Origin": "file://",
            HEADER_X_AUTH_TOKEN: "",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko)"
            ),
            HEADER_CUST_NUMBER: "",
            "Accept-Language": "zh-CN,cn;q=0.9",
        }
        self.auth_token = auth_token
        self.customer_number: str | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _make_request(
        self,
        path: str,
        payload: dict[str, Any] | None,
        with_auth: bool = True,
        method: str = "POST",
        custom_headers: dict[str, str] | None = None,
        base_path: str = BASE_PATH_APP,
    ) -> tuple[Any, dict[str, Any]]:
        """Make an HTTP request and return (headers, json_data)."""
        url = base_path + path
        headers = copy(self._common_headers)
        if custom_headers:
            headers.update(custom_headers)
        if with_auth:
            headers[HEADER_X_AUTH_TOKEN] = self.auth_token or ""
            headers[HEADER_CUST_NUMBER] = self.customer_number or ""

        _LOGGER.debug("API request: %s, data=%s, auth=%s", path, payload, with_auth)
        if method != "POST":
            raise NotImplementedError("Only POST is supported")

        response = self._session.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code != 200:
            _LOGGER.error("API %s returned HTTP %d", path, response.status_code)
            raise CSGHTTPError(response.status_code)

        json_str = response.content.decode("utf-8", errors="ignore")
        json_str = json_str[json_str.find("{") : json_str.rfind("}") + 1]
        try:
            response_data = json.loads(json_str)
        except json.JSONDecodeError as err:
            _LOGGER.error(
                "API %s returned invalid JSON response: %s", path, err
            )
            raise CSGAPIError("invalid_json", json_str[:100]) from err
        _LOGGER.debug(
            "API %s response: %s",
            path,
            json.dumps(response_data, ensure_ascii=False),
        )
        return response.headers, response_data

    def _handle_unsuccessful_response(self, api_path: str, response_data: dict[str, Any]) -> None:
        """Raise appropriate exception for non-success status codes."""
        _LOGGER.debug(
            "Unsuccessful response for %s (%s): %s",
            api_path,
            self.customer_number,
            response_data,
        )
        sta = response_data.get(JSON_KEY_STA, "unknown")
        if sta == RESP_STA_NO_LOGIN:
            raise NotLoggedIn(sta, response_data.get(JSON_KEY_MESSAGE))
        raise CSGAPIError(sta, response_data.get(JSON_KEY_MESSAGE))

    # ------------------------------------------------------------------
    # Raw API calls
    # ------------------------------------------------------------------
    def api_send_login_sms(self, phone_no: str) -> bool:
        """Request a login SMS verification code."""
        path = "center/sendMsg"
        payload = {
            JSON_KEY_AREA_CODE: AREACODE_FALLBACK,
            "phoneNumber": phone_no,
            "vcType": VERIFICATION_CODE_TYPE_LOGIN,
            "msgType": SEND_MSG_TYPE_VERIFICATION_CODE,
        }
        _, resp_data = self._make_request(path, payload, with_auth=False)
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return True
        self._handle_unsuccessful_response(path, resp_data)
        return False  # never reached

    def api_create_login_qr_code(
        self, channel: QRCodeType, login_id: str | None = None
    ) -> tuple[str, str]:
        """Create a login QR code and return (login_id, image_url)."""
        path = "center/createLoginQrcode"
        login_id = login_id or generate_qr_login_id()
        payload = {
            JSON_KEY_AREA_CODE: AREACODE_FALLBACK,
            "channel": channel,
            "lgoinId": login_id,  # intentional misspelling from upstream
        }
        _, resp_data = self._make_request(
            path, payload, with_auth=False, base_path=BASE_PATH_WEB
        )
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return login_id, resp_data[JSON_KEY_DATA]
        self._handle_unsuccessful_response(path, resp_data)
        return "", ""  # never reached

    def api_get_qr_login_status(self, login_id: str) -> tuple[bool, str]:
        """Poll QR login status; returns (success, auth_token)."""
        path = "center/getLoginInfo"
        payload = {
            JSON_KEY_AREA_CODE: AREACODE_FALLBACK,
            "loginId": login_id,
        }
        resp_header, resp_data = self._make_request(
            path, payload, with_auth=False, base_path=BASE_PATH_WEB
        )
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return True, resp_header.get(HEADER_X_AUTH_TOKEN, "")
        if resp_data[JSON_KEY_STA] == RESP_STA_QR_NOT_SCANNED:
            return False, ""
        self._handle_unsuccessful_response(path, resp_data)
        return False, ""  # never reached

    def api_login_with_sms_code(self, phone_no: str, sms_code: str) -> str:
        """Login with phone number and SMS code; returns auth token."""
        path = "center/login"
        payload = {
            JSON_KEY_AREA_CODE: AREACODE_FALLBACK,
            JSON_KEY_ACCT_ID: phone_no,
            JSON_KEY_LOGON_CHAN: LOGON_CHANNEL_HANDHELD_HALL,
            JSON_KEY_CRED_TYPE: LOGIN_TYPE_PHONE_CODE,
            JSON_KEY_SMS_CODE: sms_code,
        }
        payload = {JSON_KEY_PARAM: encrypt_params(payload)}
        resp_header, resp_data = self._make_request(
            path,
            payload,
            with_auth=False,
            custom_headers={"need-crypto": "true"},
        )
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return resp_header.get(HEADER_X_AUTH_TOKEN, "")
        self._handle_unsuccessful_response(path, resp_data)
        return ""  # never reached

    def api_login_with_password_and_sms_code(
        self, phone_no: str, password: str, sms_code: str
    ) -> str:
        """Login with phone number, password and SMS code; returns auth token."""
        path = "center/loginByPwdAndMsg"
        payload = {
            JSON_KEY_AREA_CODE: AREACODE_FALLBACK,
            JSON_KEY_ACCT_ID: phone_no,
            JSON_KEY_LOGON_CHAN: LOGON_CHANNEL_HANDHELD_HALL,
            JSON_KEY_CRED_TYPE: LOGIN_TYPE_PHONE_PWD_CODE,
            "credentials": encrypt_credential(password),
            JSON_KEY_SMS_CODE: sms_code,
            "checkPwd": True,
        }
        payload = {JSON_KEY_PARAM: encrypt_params(payload)}
        resp_header, resp_data = self._make_request(
            path,
            payload,
            with_auth=False,
            custom_headers={"need-crypto": "true"},
        )
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return resp_header.get(HEADER_X_AUTH_TOKEN, "")
        if resp_data[JSON_KEY_STA] == RESP_STA_LOGIN_WRONG_CREDENTIAL:
            raise InvalidCredentials(
                resp_data[JSON_KEY_STA], resp_data.get(JSON_KEY_MESSAGE)
            )
        self._handle_unsuccessful_response(path, resp_data)
        return ""  # never reached

    def api_query_authentication_result(self) -> dict[str, Any]:
        """Verify current session."""
        path = "user/queryAuthenticationResult"
        _, resp_data = self._make_request(path, None)
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return resp_data[JSON_KEY_DATA]
        self._handle_unsuccessful_response(path, resp_data)
        return {}

    def api_get_user_info(self) -> dict[str, Any]:
        """Get account user info."""
        path = "user/getUserInfo"
        _, resp_data = self._make_request(path, None)
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return resp_data[JSON_KEY_DATA]
        self._handle_unsuccessful_response(path, resp_data)
        return {}

    def api_get_all_linked_electricity_accounts(self) -> list[dict[str, Any]]:
        """List all linked electricity accounts."""
        path = "eleCustNumber/queryBindEleUsers"
        _, resp_data = self._make_request(path, {})
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return resp_data[JSON_KEY_DATA]
        self._handle_unsuccessful_response(path, resp_data)
        return []

    def api_get_metering_point(self, area_code: str, ele_customer_id: str) -> dict[str, Any]:
        """Get metering point id for an electricity account."""
        path = "charge/queryMeteringPoint"
        payload = {
            JSON_KEY_AREA_CODE: area_code,
            "eleCustNumberList": [
                {JSON_KEY_ELE_CUST_ID: ele_customer_id, JSON_KEY_AREA_CODE: area_code}
            ],
        }
        _, resp_data = self._make_request(path, payload)
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return resp_data[JSON_KEY_DATA]
        self._handle_unsuccessful_response(path, resp_data)
        return {}

    def api_query_day_electric_by_m_point(
        self,
        year: int,
        month: int,
        area_code: str,
        ele_customer_id: str,
        metering_point_id: str,
    ) -> dict[str, Any]:
        """Daily kWh usage for a given month."""
        path = "charge/queryDayElectricByMPoint"
        payload = {
            JSON_KEY_AREA_CODE: area_code,
            JSON_KEY_ELE_CUST_ID: ele_customer_id,
            JSON_KEY_YEAR_MONTH: f"{year}{month:02d}",
            JSON_KEY_METERING_POINT_ID: metering_point_id,
        }
        _, resp_data = self._make_request(path, payload)
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return resp_data[JSON_KEY_DATA]
        self._handle_unsuccessful_response(path, resp_data)
        return {}

    def api_query_day_electric_charge_by_m_point(
        self,
        year: int,
        month: int,
        area_code: str,
        ele_customer_id: str,
        metering_point_id: str,
    ) -> dict[str, Any]:
        """Daily cost and ladder info for a given month."""
        path = "charge/queryDayElectricChargeByMPoint"
        payload = {
            JSON_KEY_AREA_CODE: area_code,
            JSON_KEY_ELE_CUST_ID: ele_customer_id,
            JSON_KEY_YEAR_MONTH: f"{year}{month:02d}",
            JSON_KEY_METERING_POINT_ID: metering_point_id,
        }
        _, resp_data = self._make_request(path, payload)
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return resp_data[JSON_KEY_DATA]
        self._handle_unsuccessful_response(path, resp_data)
        return {}

    def api_query_account_surplus(
        self, area_code: str, ele_customer_id: str
    ) -> dict[str, Any]:
        """Balance and arrears."""
        path = "charge/queryUserAccountNumberSurplus"
        payload = {
            JSON_KEY_AREA_CODE: area_code,
            JSON_KEY_ELE_CUST_ID: ele_customer_id,
        }
        _, resp_data = self._make_request(path, payload)
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return resp_data[JSON_KEY_DATA]
        self._handle_unsuccessful_response(path, resp_data)
        return {}

    def api_get_fee_analyze_details(
        self, year: int, area_code: str, ele_customer_id: str
    ) -> dict[str, Any]:
        """Year total kWh, cost and monthly breakdown."""
        path = "charge/getAnalyzeFeeDetails"
        payload = {
            JSON_KEY_AREA_CODE: area_code,
            "electricityBillYear": year,
            JSON_KEY_ELE_CUST_ID: ele_customer_id,
            JSON_KEY_METERING_POINT_ID: None,
        }
        _, resp_data = self._make_request(path, payload)
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return resp_data[JSON_KEY_DATA]
        self._handle_unsuccessful_response(path, resp_data)
        return {}

    def api_query_day_electric_by_m_point_yesterday(
        self, area_code: str, ele_customer_id: str
    ) -> dict[str, Any]:
        """Yesterday's power consumption."""
        path = "charge/queryDayElectricByMPointYesterday"
        payload = {
            JSON_KEY_ELE_CUST_ID: ele_customer_id,
            JSON_KEY_AREA_CODE: area_code,
        }
        _, resp_data = self._make_request(path, payload)
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return resp_data[JSON_KEY_DATA]
        self._handle_unsuccessful_response(path, resp_data)
        return {}

    def api_logout(self, logon_chan: str, cred_type: str) -> dict[str, Any]:
        """Logout the current session."""
        path = "center/logout"
        payload = {
            JSON_KEY_LOGON_CHAN: logon_chan,
            JSON_KEY_CRED_TYPE: cred_type,
        }
        _, resp_data = self._make_request(path, payload)
        if resp_data[JSON_KEY_STA] == RESP_STA_SUCCESS:
            return resp_data[JSON_KEY_DATA]
        self._handle_unsuccessful_response(path, resp_data)
        return {}

    # ------------------------------------------------------------------
    # Session utilities
    # ------------------------------------------------------------------
    @staticmethod
    def load(data: dict[str, Any]) -> CSGClient:
        """Restore a client from persisted session data."""
        if not data.get(ATTR_AUTH_TOKEN):
            raise ValueError("missing parameter: auth_token")
        return CSGClient(auth_token=data[ATTR_AUTH_TOKEN])

    def dump(self) -> dict[str, Any]:
        """Persist the current session."""
        return {ATTR_AUTH_TOKEN: self.auth_token}

    def set_authentication_params(self, auth_token: str) -> None:
        """Set the authentication token."""
        self.auth_token = auth_token

    def initialize(self) -> None:
        """Initialize the client (must be called after login)."""
        resp_data = self.api_get_user_info()
        self.customer_number = resp_data.get(JSON_KEY_CUST_NUMBER)

    def verify_login(self) -> bool:
        """Return True if the current session is still valid."""
        try:
            self.api_query_authentication_result()
        except NotLoggedIn:
            return False
        return True

    def logout(self, login_type: Any) -> None:
        """Logout and reset the session."""
        # login_type can be a LoginType enum or the plain string persisted in
        # config entry data. str(LoginType.X) yields "LoginType.X" rather than
        # the value, so normalize explicitly.
        cred_type = str(getattr(login_type, "value", login_type))
        self.api_logout(LOGON_CHANNEL_HANDHELD_HALL, cred_type)
        self.auth_token = None
        self.customer_number = None

    # ------------------------------------------------------------------
    # High-level wrappers
    # ------------------------------------------------------------------
    def get_all_electricity_accounts(self) -> list[CSGElectricityAccount]:
        """Fetch all linked electricity accounts with metering points."""
        result: list[CSGElectricityAccount] = []
        ele_users = self.api_get_all_linked_electricity_accounts()

        for item in ele_users:
            area_code = item.get(JSON_KEY_AREA_CODE)
            binding_id = item.get("bindingId")
            if not area_code or not binding_id:
                _LOGGER.warning(
                    "Skipping linked electricity account with missing keys: %s",
                    item,
                )
                continue
            metering_data = self.api_get_metering_point(area_code, binding_id)
            if not metering_data:
                continue
            mp = metering_data[0]
            result.append(
                CSGElectricityAccount(
                    account_number=item["eleCustNumber"],
                    area_code=area_code,
                    ele_customer_id=binding_id,
                    metering_point_id=mp.get(JSON_KEY_METERING_POINT_ID),
                    metering_point_number=mp.get(JSON_KEY_METERING_POINT_NUMBER),
                    address=item.get("eleAddress"),
                    user_name=item.get("userName"),
                )
            )
        return result

    def get_month_daily_usage_detail(
        self, account: CSGElectricityAccount, year_month: tuple[int, int]
    ) -> tuple[float, list[dict[str, str | float]]]:
        """Get total kWh and per-day usage for a month."""
        year, month = year_month
        resp = self.api_query_day_electric_by_m_point(
            year,
            month,
            account.area_code,
            account.ele_customer_id,
            account.metering_point_id,
        )
        month_total = safe_float(resp.get("totalPower"), 0.0) or 0.0
        by_day = [
            {"date": d["date"], "kwh": safe_float(d.get("power"), 0.0) or 0.0}
            for d in resp.get("result", [])
        ]
        return month_total, by_day

    def get_month_daily_cost_detail(
        self, account: CSGElectricityAccount, year_month: tuple[int, int]
    ) -> tuple[float | None, float | None, dict[str, Any], list[dict[str, Any]]]:
        """Get total cost, total kWh, ladder info and per-day cost data."""
        year, month = year_month
        resp = self.api_query_day_electric_charge_by_m_point(
            year,
            month,
            account.area_code,
            account.ele_customer_id,
            account.metering_point_id,
        )

        by_day = [
            {
                "date": d["date"],
                "charge": safe_float(d.get("charge"), 0.0) or 0.0,
                "kwh": safe_float(d.get("power"), 0.0) or 0.0,
            }
            for d in resp.get("result", [])
        ]

        month_total_cost = safe_float(resp.get("totalElectricity"))
        month_total_kwh = safe_float(resp.get("totalPower"))

        ladder = {
            "ladder": (
                int(resp["ladderEle"])
                if resp.get("ladderEle") is not None
                and str(resp["ladderEle"]).lstrip("-").isdigit()
                else None
            ),
            "start_date": (
                datetime.datetime.strptime(
                    resp["ladderEleStartDate"], "%Y-%m-%d %H:%M:%S.%f"
                )
                if resp.get("ladderEleStartDate")
                else None
            ),
            "remaining_kwh": safe_float(resp.get("ladderEleSurplus")),
            "tariff": safe_float(resp.get("ladderEleTariff")),
        }

        return month_total_cost, month_total_kwh, ladder, by_day

    def get_balance_and_arrears(
        self, account: CSGElectricityAccount
    ) -> tuple[float, float]:
        """Return (balance, arrears) for an account."""
        resp = self.api_query_account_surplus(
            account.area_code, account.ele_customer_id
        )
        data = resp[0] if isinstance(resp, list) else resp
        balance = safe_float(data.get("balance"), 0.0) or 0.0
        arrears = safe_float(data.get("arrears"), 0.0) or 0.0
        return balance, arrears

    def get_year_month_stats(
        self, account: CSGElectricityAccount, year: int
    ) -> tuple[float, float, list[dict[str, str | float]]]:
        """Return (total_cost, total_kWh, monthly_breakdown)."""
        resp = self.api_get_fee_analyze_details(
            year, account.area_code, account.ele_customer_id
        )
        total_kwh = safe_float(resp.get("totalBillingElectricity"), 0.0) or 0.0
        total_cost = safe_float(resp.get("totalActualAmount"), 0.0) or 0.0
        by_month = [
            {
                "month": m[JSON_KEY_YEAR_MONTH],
                "charge": safe_float(m.get("actualTotalAmount"), 0.0) or 0.0,
                "kwh": safe_float(m.get("billingElectricity"), 0.0) or 0.0,
            }
            for m in resp.get("electricAndChargeList", [])
        ]
        return float(total_cost), float(total_kwh), by_month

    def get_yesterday_kwh(self, account: CSGElectricityAccount) -> float | None:
        """Get yesterday's power consumption."""
        resp = self.api_query_day_electric_by_m_point_yesterday(
            account.area_code, account.ele_customer_id
        )
        return safe_float(resp.get("power"))
