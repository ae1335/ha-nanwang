"""Unit tests for the csg_power api layer (no Home Assistant required).

Run from the repository root:
    python -m pytest tests/ -v
"""

from __future__ import annotations

import json
import unittest.mock as mock

import pytest

from custom_components.csg_power.api import (  # noqa: E402
    CSGElectricityAccount,
    CSGClient,
    CSGAPIError,
    CSGHTTPError,
    LoginType,
    NotLoggedIn,
    decrypt_params,
    encrypt_params,
    generate_qr_login_id,
    safe_float,
)
from custom_components.csg_power.utils import (  # noqa: E402
    STATE_UNAVAILABLE,
    merge_by_day_data,
)

# ---------------------------------------------------------------------------
# safe_float
# ---------------------------------------------------------------------------


class TestSafeFloat:
    def test_valid_numbers(self):
        assert safe_float("12.5") == 12.5
        assert safe_float("42") == 42.0
        assert safe_float(3.14) == 3.14
        assert safe_float(-1) == -1.0

    def test_none_returns_default(self):
        assert safe_float(None) is None
        assert safe_float(None, 0.0) == 0.0

    def test_empty_string_returns_default(self):
        assert safe_float("") is None
        assert safe_float("", 1.0) == 1.0

    def test_invalid_string_returns_default(self):
        assert safe_float("abc") is None
        assert safe_float("abc", -1.0) == -1.0


# ---------------------------------------------------------------------------
# AES encrypt / decrypt round-trip
# ---------------------------------------------------------------------------


class TestEncryptRoundTrip:
    def test_ascii_round_trip(self):
        payload = {"acctId": "13800138000", "code": "123456"}
        encrypted = encrypt_params(payload)
        assert decrypt_params(encrypted) == payload

    def test_chinese_round_trip(self):
        # ensure_ascii=False path: Chinese characters must survive
        payload = {"message": "南方电网", "address": "广州市天河区"}
        encrypted = encrypt_params(payload)
        assert decrypt_params(encrypted) == payload

    def test_empty_dict_round_trip(self):
        encrypted = encrypt_params({})
        assert decrypt_params(encrypted) == {}

    def test_ciphertext_is_base64(self):
        import base64

        encrypted = encrypt_params({"a": 1})
        # Must be decodable base64 without error
        base64.b64decode(encrypted, validate=True)


# ---------------------------------------------------------------------------
# generate_qr_login_id
# ---------------------------------------------------------------------------


def test_generate_qr_login_id_is_md5_hex():
    login_id = generate_qr_login_id()
    assert len(login_id) == 32
    int(login_id, 16)  # raises if not hexadecimal


# ---------------------------------------------------------------------------
# CSGElectricityAccount serialization
# ---------------------------------------------------------------------------


class TestElectricityAccount:
    def _sample(self) -> CSGElectricityAccount:
        return CSGElectricityAccount(
            account_number="1234567890",
            area_code="030000",
            ele_customer_id="cust-1",
            metering_point_id="mp-1",
            metering_point_number="mpn-1",
            address="广州",
            user_name="张三",
        )

    def test_dump_load_round_trip(self):
        account = self._sample()
        restored = CSGElectricityAccount.load(account.dump())
        assert restored.account_number == account.account_number
        assert restored.area_code == account.area_code
        assert restored.ele_customer_id == account.ele_customer_id
        assert restored.metering_point_id == account.metering_point_id
        assert restored.metering_point_number == account.metering_point_number
        assert restored.address == account.address
        assert restored.user_name == account.user_name

    def test_load_missing_key_raises(self):
        data = self._sample().dump()
        del data["account_number"]
        with pytest.raises(ValueError, match="account_number"):
            CSGElectricityAccount.load(data)

    def test_metering_point_number_is_optional(self):
        data = self._sample().dump()
        del data["metering_point_number"]
        restored = CSGElectricityAccount.load(data)
        assert restored.metering_point_number is None


# ---------------------------------------------------------------------------
# merge_by_day_data (moved to utils for testability)
# ---------------------------------------------------------------------------


class TestMergeByDayData:
    def test_both_unavailable(self):
        by_day, kwh = merge_by_day_data(
            by_day_from_cost=STATE_UNAVAILABLE,
            kwh_from_cost=STATE_UNAVAILABLE,
            by_day_from_usage=STATE_UNAVAILABLE,
            kwh_from_usage=STATE_UNAVAILABLE,
        )
        assert by_day == STATE_UNAVAILABLE
        assert kwh == STATE_UNAVAILABLE

    def test_cost_unavailable_falls_back_to_usage(self):
        usage = [{"date": "01", "kwh": 1.0}]
        by_day, kwh = merge_by_day_data(
            by_day_from_cost=STATE_UNAVAILABLE,
            kwh_from_cost=STATE_UNAVAILABLE,
            by_day_from_usage=usage,
            kwh_from_usage=5.0,
        )
        assert by_day == usage
        assert kwh == 5.0

    def test_usage_unavailable_falls_back_to_cost(self):
        cost = [{"date": "01", "kwh": 1.0, "charge": 0.5}]
        by_day, kwh = merge_by_day_data(
            by_day_from_cost=cost,
            kwh_from_cost=5.0,
            by_day_from_usage=STATE_UNAVAILABLE,
            kwh_from_usage=STATE_UNAVAILABLE,
        )
        assert by_day == cost
        assert kwh == 5.0

    def test_cost_longer_wins(self):
        cost = [
            {"date": "01", "kwh": 1.0, "charge": 0.5},
            {"date": "02", "kwh": 2.0, "charge": 1.0},
        ]
        usage = [{"date": "01", "kwh": 1.0}]
        by_day, kwh = merge_by_day_data(
            by_day_from_cost=cost,
            kwh_from_cost=3.0,
            by_day_from_usage=usage,
            kwh_from_usage=3.0,
        )
        assert by_day == cost
        assert kwh == 3.0  # equal -> max

    def test_usage_longer_gets_charges_patched(self):
        cost = [{"date": "01", "kwh": 1.0, "charge": 0.5}]
        usage = [
            {"date": "01", "kwh": 1.0, "charge": 9.9},
            {"date": "02", "kwh": 2.0, "charge": 9.9},
        ]
        by_day, kwh = merge_by_day_data(
            by_day_from_cost=cost,
            kwh_from_cost=3.0,
            by_day_from_usage=usage,
            kwh_from_usage=3.0,
        )
        # usage list is the base, patched with cost charges for overlap
        assert by_day[0]["charge"] == 0.5
        assert by_day[1]["date"] == "02"
        assert by_day[1]["charge"] == 9.9
        assert kwh == 3.0

    def test_kwh_takes_max(self):
        merge = merge_by_day_data(
            by_day_from_cost=[{"date": "01", "kwh": 1.0, "charge": 0.5}],
            kwh_from_cost=2.0,
            by_day_from_usage=[{"date": "01", "kwh": 1.0}],
            kwh_from_usage=3.0,
        )
        assert merge[1] == 3.0


# ---------------------------------------------------------------------------
# CSGClient._make_request / session helpers (mocked HTTP)
# ---------------------------------------------------------------------------


def _mk_response(status_code: int, body: bytes, headers: dict | None = None):
    resp = mock.Mock()
    resp.status_code = status_code
    resp.content = body
    resp.headers = headers or {}
    return resp


class TestMakeRequest:
    def _client(self) -> CSGClient:
        client = CSGClient(auth_token="token-1")
        client.customer_number = "cust-1"
        return client

    def test_success_returns_headers_and_json(self):
        client = self._client()
        body = json.dumps({"sta": "00", "data": {"kwh": 1}}).encode()
        client._session = mock.Mock()
        client._session.post.return_value = _mk_response(
            200, body, {"x-auth-token": "t"}
        )
        headers, data = client._make_request("user/getUserInfo", None)
        assert data["sta"] == "00"
        # timeout must be passed to the HTTP layer
        assert client._session.post.call_args.kwargs["timeout"] == 30

    def test_non_200_raises_http_error(self):
        client = self._client()
        client._session = mock.Mock()
        client._session.post.return_value = _mk_response(502, b"Bad Gateway")
        with pytest.raises(CSGHTTPError) as exc_info:
            client._make_request("user/getUserInfo", None)
        assert exc_info.value.status_code == 502

    def test_invalid_json_raises_api_error(self):
        client = self._client()
        client._session = mock.Mock()
        client._session.post.return_value = _mk_response(200, b"<html>oops</html>")
        with pytest.raises(CSGAPIError, match="invalid_json"):
            client._make_request("user/getUserInfo", None)

    def test_auth_headers_attached(self):
        client = self._client()
        body = json.dumps({"sta": "00", "data": {}}).encode()
        client._session = mock.Mock()
        client._session.post.return_value = _mk_response(200, body)
        client._make_request("user/getUserInfo", None)
        sent_headers = client._session.post.call_args.kwargs["headers"]
        assert sent_headers["x-auth-token"] == "token-1"
        assert sent_headers["custNumber"] == "cust-1"


class TestClientSessionHelpers:
    def test_verify_login_true(self):
        client = CSGClient(auth_token="t")
        with mock.patch.object(
            CSGClient, "api_query_authentication_result", return_value={"ok": True}
        ):
            assert client.verify_login() is True

    def test_verify_login_false_on_not_logged_in(self):
        client = CSGClient(auth_token="t")
        with mock.patch.object(
            CSGClient,
            "api_query_authentication_result",
            side_effect=NotLoggedIn("04", "expired"),
        ):
            assert client.verify_login() is False

    def test_logout_normalizes_enum(self):
        client = CSGClient(auth_token="t")
        with mock.patch.object(CSGClient, "api_logout") as api_logout:
            client.logout(LoginType.LOGIN_TYPE_SMS)
        # LoginType enum must be converted to its raw value "11", not
        # "LoginType.LOGIN_TYPE_SMS"
        assert api_logout.call_args.args == ("4", "11")
        assert client.auth_token is None

    def test_logout_accepts_plain_string(self):
        client = CSGClient(auth_token="t")
        with mock.patch.object(CSGClient, "api_logout") as api_logout:
            client.logout("20")
        assert api_logout.call_args.args == ("4", "20")

    def test_load_requires_auth_token(self):
        with pytest.raises(ValueError, match="auth_token"):
            CSGClient.load({})
