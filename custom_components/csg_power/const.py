"""Constants for the China Southern Power Grid integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "csg_power"

CONF_ACCOUNT_NUMBER = "account_number"
CONF_ELE_ACCOUNTS = "accounts"
CONF_LOGIN_TYPE = "login_type"
CONF_AUTH_TOKEN = "auth_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_SMS_CODE = "sms_code"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_SETTINGS = "settings"
CONF_UPDATED_AT = "updated_at"
CONF_ACTION = "action"
CONF_REFRESH_QR_CODE = "refresh_qr_code"

STEP_USER = "user"
STEP_SMS_LOGIN = "sms_login"
STEP_SMS_PWD_LOGIN = "sms_pwd_login"
STEP_VALIDATE_SMS_CODE = "validate_sms_code"
STEP_CSG_QR_LOGIN = "csg_qr_login"
STEP_WX_QR_LOGIN = "wx_qr_login"
STEP_ALI_QR_LOGIN = "ali_qr_login"
STEP_QR_LOGIN = "qr_login"
STEP_VALIDATE_QR_LOGIN = "validate_qr_login"
STEP_INIT = "init"
STEP_SETTINGS = "settings"
STEP_ADD_ACCOUNT = "add_account"

ABORT_NO_ACCOUNT = "no_account"
ABORT_ALL_ADDED = "all_added"

ERROR_CANNOT_CONNECT = "cannot_connect"
ERROR_INVALID_AUTH = "invalid_auth"
ERROR_UNKNOWN = "unknown"
ERROR_QR_NOT_SCANNED = "qr_not_scanned"

DEFAULT_UPDATE_INTERVAL = timedelta(hours=4).seconds
SETTING_UPDATE_TIMEOUT = 60
SETTING_LAST_MONTH_UPDATE_DAY_THRESHOLD = 3
SETTING_LAST_YEAR_UPDATE_DAY_THRESHOLD = 7

DATA_KEY_LAST_UPDATE_DAY = "last_update_day"
STATE_UPDATE_UNCHANGED = "unchanged"

SUFFIX_BAL = "balance"
SUFFIX_ARR = "arrears"
SUFFIX_YESTERDAY_KWH = "yesterday_kwh"
SUFFIX_LATEST_DAY_KWH = "latest_day_kwh"
SUFFIX_LATEST_DAY_COST = "latest_day_cost"
SUFFIX_THIS_YEAR_KWH = "this_year_total_usage"
SUFFIX_THIS_YEAR_COST = "this_year_total_cost"
SUFFIX_THIS_MONTH_KWH = "this_month_total_usage"
SUFFIX_THIS_MONTH_COST = "this_month_total_cost"
SUFFIX_CURRENT_LADDER = "current_ladder"
SUFFIX_CURRENT_LADDER_REMAINING_KWH = "current_ladder_remaining_kwh"
SUFFIX_CURRENT_LADDER_TARIFF = "current_ladder_tariff"
SUFFIX_LAST_YEAR_KWH = "last_year_total_usage"
SUFFIX_LAST_YEAR_COST = "last_year_total_cost"
SUFFIX_LAST_MONTH_KWH = "last_month_total_usage"
SUFFIX_LAST_MONTH_COST = "last_month_total_cost"

ATTR_KEY_THIS_MONTH_BY_DAY = "this_month_by_day"
ATTR_KEY_THIS_YEAR_BY_MONTH = "this_year_by_month"
ATTR_KEY_LAST_MONTH_BY_DAY = "last_month_by_day"
ATTR_KEY_LAST_YEAR_BY_MONTH = "last_year_by_month"
ATTR_KEY_LATEST_DAY_DATE = "latest_day_date"
ATTR_KEY_CURRENT_LADDER_START_DATE = "current_ladder_start_date"

WF_ATTR_LADDER = "ladder"
WF_ATTR_LADDER_START_DATE = "start_date"
WF_ATTR_LADDER_REMAINING_KWH = "remaining_kwh"
WF_ATTR_LADDER_TARIFF = "tariff"
WF_ATTR_DATE = "date"
WF_ATTR_MONTH = "month"
WF_ATTR_CHARGE = "charge"
WF_ATTR_KWH = "kwh"
