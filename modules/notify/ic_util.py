# ic_util.py
import requests
from urllib.parse import urlencode
import logging
logger = logging.getLogger(__name__)

IC_API_URL = "https://im-api.skyunion.net/msg"


def _clean(x):
    if x is None:
        return ""
    if not isinstance(x, str):
        x = str(x)
    return x.encode("utf-8", errors="ignore").decode("utf-8")


def _post(payload):

    payload_json = str(payload)

    logger.info("ic_util._post payload: %s", payload_json)
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    resp = requests.post(IC_API_URL, data=urlencode(
        payload), headers=headers, timeout=5)

    resp_json = str(resp)
    try:
        resp_json = resp.json()
    except Exception:
        logger.exception("_post resp.json() failed")
    logger.info("ic_util._post return：: %s", resp_json)
    return resp_json


# -------------------------------------------------------------------------
# 群消息（自动按 project 查 token 和默认群号）
# -------------------------------------------------------------------------
def send_to_group(token, content, room_id, *, title="", at_user=""):

    payload = {
        "token": token,
        "target": "group",
        "room": room_id,
        "title": _clean(title),
        "content": _clean(content),
        "content_type": "1"
    }

    if at_user:
        payload["at_user"] = _clean(at_user)

    return _post(payload)


# -------------------------------------------------------------------------
# 私聊（按项目取 token，但无需默认 room）
# -------------------------------------------------------------------------
def send_to_user(token, account, content, *, title="", popup=0):
    payload = {
        "token": token,
        "target": "single",
        "account": account,
        "title": _clean(title),
        "content": _clean(content),
        "content_type": "1",
        "popup_type": str(int(popup)),
    }

    return _post(payload)
