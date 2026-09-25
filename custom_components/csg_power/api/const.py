"""API constants for CSG."""

from enum import Enum

BASE_PATH_WEB = "https://95598.csg.cn/ucs/ma/wt/"
BASE_PATH_APP = "https://95598.csg.cn/ucs/ma/zt/"

PARAM_KEY = "cOdHFNHUNkZrjNaN".encode("utf8")
PARAM_IV = "oMChoRLZnTivcQyR".encode("utf8")

LOGON_CHANNEL_ONLINE_HALL = "3"
LOGON_CHANNEL_HANDHELD_HALL = "4"

RESP_STA_SUCCESS = "00"
RESP_STA_NO_LOGIN = "04"
RESP_STA_QR_NOT_SCANNED = "09"
RESP_STA_LOGIN_WRONG_CREDENTIAL = "00010002"

LOGIN_TYPE_PHONE_CODE = "11"
LOGIN_TYPE_PHONE_PWD_CODE = "1011"
SEND_MSG_TYPE_VERIFICATION_CODE = "1"
VERIFICATION_CODE_TYPE_LOGIN = "1"

AREACODE_FALLBACK = "030000"

CREDENTIAL_PUBKEY = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQD1RJE6GBKJlFQvTU6g0ws9R"
    "+qXFccKl4i1Rf4KVR8Rh3XtlBtvBxEyTxnVT294RVvYz6THzHGQwREnlgdkjZyGBf7tmV2CgwaHF+ttvupuzOmRVQ"
    "/difIJtXKM+SM0aCOqBk0fFaLiHrZlZS4qI2/rBQN8VBoVKfGinVMM+USswwIDAQAB"
)

HEADER_X_AUTH_TOKEN = "x-auth-token"
HEADER_CUST_NUMBER = "custNumber"

JSON_KEY_STA = "sta"
JSON_KEY_MESSAGE = "message"
JSON_KEY_CUST_NUMBER = "custNumber"
JSON_KEY_DATA = "data"
JSON_KEY_LOGON_CHAN = "logonChan"
JSON_KEY_SMS_CODE = "code"
JSON_KEY_CRED_TYPE = "credType"
JSON_KEY_AREA_CODE = "areaCode"
JSON_KEY_PARAM = "param"
JSON_KEY_ACCT_ID = "acctId"
JSON_KEY_ELE_CUST_ID = "eleCustId"
JSON_KEY_METERING_POINT_ID = "meteringPointId"
JSON_KEY_METERING_POINT_NUMBER = "meteringPointNumber"
JSON_KEY_YEAR_MONTH = "yearMonth"

ATTR_AUTH_TOKEN = "auth_token"
ATTR_LOGIN_TYPE = "login_type"
ATTR_ACCOUNT_NUMBER = "account_number"
ATTR_AREA_CODE = "area_code"
ATTR_ELE_CUSTOMER_ID = "ele_customer_id"
ATTR_METERING_POINT_ID = "metering_point_id"
ATTR_METERING_POINT_NUMBER = "metering_point_number"
ATTR_ADDRESS = "address"
ATTR_USER_NAME = "user_name"

QR_EXPIRY_SECONDS = 300

# Timeout (seconds) for every HTTP request. Prevents executor threads from
# hanging forever when the CSG server does not respond.
REQUEST_TIMEOUT = 30


class LoginType(str, Enum):
    LOGIN_TYPE_SMS = "11"
    LOGIN_TYPE_PWD_AND_SMS = "1011"
    LOGIN_TYPE_WX_QR = "20"
    LOGIN_TYPE_ALI_QR = "21"
    LOGIN_TYPE_CSG_QR = "30"


class QRCodeType(str, Enum):
    QR_CSG = "app"
    QR_WECHAT = "wechat"
    QR_ALIPAY = "alipay"


LOGIN_TYPE_TO_QR_CODE_TYPE = {
    LoginType.LOGIN_TYPE_CSG_QR: QRCodeType.QR_CSG,
    LoginType.LOGIN_TYPE_WX_QR: QRCodeType.QR_WECHAT,
    LoginType.LOGIN_TYPE_ALI_QR: QRCodeType.QR_ALIPAY,
}

LOGIN_TYPE_TO_QR_APP_NAME = {
    LoginType.LOGIN_TYPE_CSG_QR: "南网APP",
    LoginType.LOGIN_TYPE_WX_QR: "微信",
    LoginType.LOGIN_TYPE_ALI_QR: "支付宝",
}
