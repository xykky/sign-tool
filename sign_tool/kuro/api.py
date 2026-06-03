from __future__ import annotations

import json
import random
import asyncio
import socket
from typing import Any

import httpx

from ..log import get_logger
from .constants import (
    MAIN_URL,
    KURO_VERSION,
    PLATFORM_SOURCE,
    CONTENT_TYPE,
    IOS_USER_AGENT,
    SIGNIN_URL,
    SIGNIN_TASK_LIST_URL,
    LOGIN_URL,
    LOGIN_LOG_URL,
    REQUEST_TOKEN,
    REFRESH_URL,
    FIND_ROLE_LIST_URL,
    GET_TASK_URL,
    FORUM_LIST_URL,
    LIKE_URL,
    SIGN_IN_URL,
    POST_DETAIL_URL,
    SHARE_URL,
    SERVER_ID,
    SERVER_ID_NET,
    NET_SERVER_ID_MAP,
)

logger = get_logger()

# Error codes
CODE_TOKEN_INVALID = 220
CODE_BAT_TOKEN_INVALID = 10903
CODE_ALREADY_SIGNED = 1511
CODE_OK_ZERO = 0
CODE_OK_HTTP = 200


class KuroError(Exception):
    def __init__(self, message: str, code: int = -1, raw: Any = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.raw = raw


def _get_local_ip() -> str:
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


_PUBLIC_IP: str | None = None


async def _get_public_ip() -> str:
    global _PUBLIC_IP
    if _PUBLIC_IP:
        return _PUBLIC_IP
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get("https://event.kurobbs.com/event/ip")
            _PUBLIC_IP = r.text.strip()
            return _PUBLIC_IP
    except Exception:
        pass
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get("https://api.ipify.org/?format=json")
            _PUBLIC_IP = r.json()["ip"]
            return _PUBLIC_IP
    except Exception:
        pass
    _PUBLIC_IP = _get_local_ip()
    return _PUBLIC_IP


def _base_headers(dev_code: str = "") -> dict[str, str]:
    return {
        "source": PLATFORM_SOURCE,
        "Content-Type": CONTENT_TYPE,
        "User-Agent": IOS_USER_AGENT,
        "version": KURO_VERSION,
        "devCode": dev_code or f"{_get_local_ip()}, {IOS_USER_AGENT}",
    }


class KuroClient:
    def __init__(self, cookie: str, uid: str, game_id: int, did: str = ""):
        self.cookie = cookie
        self.uid = uid
        self.game_id = game_id
        self.did = did or f"CLI-{random.randint(100000, 999999)}"
        self.bat = ""
        self.server_id = ""  # Will be set from role list if available

    async def _request(
        self,
        url: str,
        data: dict[str, Any],
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
        use_did_as_devcode: bool = True,
    ) -> dict[str, Any]:
        h = _base_headers(self.did if use_did_as_devcode else "")
        if headers:
            h.update(headers)

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(url, headers=h, data=data)
                    raw = resp.json()
                    # Parse nested data field
                    if isinstance(raw, dict) and isinstance(raw.get("data"), str):
                        try:
                            raw["data"] = json.loads(raw["data"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    return raw
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(1.0 * (attempt + 1))
                else:
                    raise KuroError(f"网络请求失败: {url}") from e
        raise KuroError(f"请求失败: {url}")

    async def _authed_request(
        self,
        url: str,
        data: dict[str, Any],
        need_token: bool = False,
    ) -> dict[str, Any]:
        headers = {
            "did": self.did,
            "b-at": self.bat,
        }
        if need_token:
            headers["token"] = self.cookie
        return await self._request(url, data, headers)

    async def login_log(self) -> bool:
        """Validate login session (pre-heat for refresh_data)."""
        headers = {
            "token": self.cookie,
            "devCode": self.did,
            "version": KURO_VERSION,
        }
        result = await self._request(LOGIN_LOG_URL, {}, headers)
        code = result.get("code", -1)
        if code == CODE_TOKEN_INVALID:
            return False
        return code in (CODE_OK_ZERO, CODE_OK_HTTP)

    def _is_net(self) -> bool:
        try:
            return int(self.uid) >= 200000000
        except (ValueError, TypeError):
            return False

    def _get_server_id(self) -> str:
        if self.server_id:
            return self.server_id
        if self._is_net():
            # 国际服: 根据 UID 前缀映射 serverId
            prefix = int(self.uid) // 100000000
            return NET_SERVER_ID_MAP.get(prefix, SERVER_ID_NET)
        return SERVER_ID

    async def login(self, mobile: str, code: str) -> dict[str, Any]:
        """SMS login. Returns {"token": "..."} on success."""
        data = {"mobile": mobile, "code": code, "devCode": self.did}
        result = await self._request(LOGIN_URL, data)
        if result.get("code") not in (CODE_OK_ZERO, CODE_OK_HTTP):
            raise KuroError(
                result.get("msg", "登录失败"),
                code=result.get("code", -1),
                raw=result,
            )
        return result.get("data", {})

    async def validate_login(self) -> bool:
        """Check if cookie is still valid."""
        headers = {
            "token": self.cookie,
            "devCode": self.did,
            "version": KURO_VERSION,
        }
        logger.info(f"[validate_login] URL: {LOGIN_LOG_URL}")
        logger.info(f"[validate_login] headers: {headers}")
        data = await self._request(LOGIN_LOG_URL, {}, headers)
        code = data.get("code", -1)
        logger.info(f"[validate_login] response: code={code}, msg={data.get('msg', '')}, data={data.get('data', '')}")
        if code == CODE_TOKEN_INVALID:
            return False
        return code in (CODE_OK_ZERO, CODE_OK_HTTP)

    async def refresh_data(self) -> dict[str, Any]:
        """Refresh game data. Build request exactly matching RoverSign."""
        ip = await _get_public_ip()
        headers = {
            "source": PLATFORM_SOURCE,
            "Content-Type": CONTENT_TYPE,
            "User-Agent": IOS_USER_AGENT,
            "version": KURO_VERSION,
            "devCode": f"{ip}, {IOS_USER_AGENT}",
            "did": self.did,
            "b-at": self.bat,
        }
        data = {
            "gameId": self.game_id,
            "serverId": self._get_server_id(),
            "roleId": self.uid,
        }
        logger.info(f"[refresh_data] URL: {REFRESH_URL}")
        logger.info(f"[refresh_data] headers: {headers}")
        logger.info(f"[refresh_data] data: {data}")
        logger.info(f"[refresh_data] public_ip: {ip}")
        logger.info(f"[refresh_data] self.did: {self.did}")
        logger.info(f"[refresh_data] self.bat: {self.bat}")
        logger.info(f"[refresh_data] self.uid: {self.uid}")
        logger.info(f"[refresh_data] self.game_id: {self.game_id}")
        logger.info(f"[refresh_data] server_id: {self._get_server_id()}")
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(REFRESH_URL, headers=headers, data=data)
                    logger.info(f"[refresh_data] status_code: {resp.status_code}")
                    logger.info(f"[refresh_data] response_headers: {dict(resp.headers)}")
                    logger.info(f"[refresh_data] response_body: {resp.text}")
                    result = resp.json()
                    if isinstance(result, dict) and isinstance(result.get("data"), str):
                        try:
                            result["data"] = json.loads(result["data"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    logger.info(f"[refresh_data] parsed result: {result}")
                    break
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                logger.error(f"[refresh_data] attempt {attempt+1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))
                else:
                    raise KuroError(f"网络请求失败: {REFRESH_URL}") from e

        code = result.get("code", -1)
        logger.info(f"[refresh_data] response code={code}, msg={result.get('msg', '')}")
        if code == CODE_BAT_TOKEN_INVALID:
            raise KuroError("BAT token 已失效", code=code)
        if code not in (CODE_OK_ZERO, CODE_OK_HTTP):
            raise KuroError(
                result.get("msg", "刷新数据失败"),
                code=code,
                raw=result,
            )
        return result

    async def refresh_bat_token(self) -> str:
        """Request a new BAT token. Returns new token string."""
        headers = {
            "token": self.cookie,
            "did": self.did,
            "b-at": "",
        }
        data = {
            "serverId": self._get_server_id(),
            "roleId": self.uid,
        }
        result = await self._request(REQUEST_TOKEN, data, headers)
        if result.get("success") or result.get("code") in (CODE_OK_ZERO, CODE_OK_HTTP):
            token = (result.get("data") or {}).get("accessToken", "")
            if token:
                self.bat = token
                return token
        raise KuroError("获取 BAT token 失败", raw=result)

    async def sign_in(self) -> dict[str, Any]:
        """Execute game sign-in."""
        # First check if already signed
        task_list = await self._sign_in_task_list()
        is_signed = False
        if isinstance(task_list, dict):
            is_signed = task_list.get("isSigIn", False)

        if is_signed:
            return {"already_signed": True, "msg": "今日已签到"}

        headers = {
            "token": self.cookie,
            "did": self.did,
            "b-at": self.bat,
            "devcode": "",
        }
        data = {
            "gameId": self.game_id,
            "serverId": self._get_server_id(),
            "roleId": self.uid,
            "reqMonth": f"{__import__('datetime').datetime.now().month:02}",
        }
        result = await self._request(SIGNIN_URL, data, headers)
        code = result.get("code", -1)
        if code == CODE_ALREADY_SIGNED:
            return {"already_signed": True, "msg": "今日已签到"}
        if code not in (CODE_OK_ZERO, CODE_OK_HTTP):
            raise KuroError(
                result.get("msg", "签到失败"),
                code=code,
                raw=result,
            )
        return {"already_signed": False, "msg": "签到成功", "data": result.get("data")}

    async def _sign_in_task_list(self) -> dict[str, Any]:
        """Check sign-in status."""
        headers = {
            "token": self.cookie,
            "did": self.did,
            "b-at": self.bat,
            "devcode": "",
        }
        data = {
            "gameId": self.game_id,
            "serverId": self._get_server_id(),
            "roleId": self.uid,
        }
        result = await self._request(SIGNIN_TASK_LIST_URL, data, headers)
        if result.get("code") in (CODE_OK_ZERO, CODE_OK_HTTP):
            return result.get("data", {})
        return {}

    async def find_role_list(self) -> list[dict[str, Any]]:
        """Get game role list (for PGR serverId)."""
        headers = {
            "token": self.cookie,
            "did": self.did,
            "b-at": self.bat,
        }
        data = {"gameId": self.game_id}
        result = await self._request(FIND_ROLE_LIST_URL, data, headers)
        if result.get("code") in (CODE_OK_ZERO, CODE_OK_HTTP):
            return result.get("data", []) if isinstance(result.get("data"), list) else []
        return []

    # BBS methods

    async def bbs_sign_in(self) -> dict[str, Any]:
        """BBS daily check-in."""
        headers = {
            "token": self.cookie,
            "did": self.did,
            "b-at": self.bat,
        }
        data = {"gameId": "2"}
        result = await self._request(SIGN_IN_URL, data, headers)
        code = result.get("code", -1)
        if code not in (CODE_OK_ZERO, CODE_OK_HTTP):
            # Already signed is not an error
            if "已签" in result.get("msg", "") or "重复" in result.get("msg", ""):
                return {"already_signed": True}
            raise KuroError(result.get("msg", "BBS签到失败"), code=code, raw=result)
        return {"already_signed": False, "data": result.get("data")}

    async def get_bbs_tasks(self) -> list[dict[str, Any]]:
        """Get BBS daily task progress."""
        headers = {
            "token": self.cookie,
            "did": self.did,
            "b-at": self.bat,
        }
        data = {"gameId": "0"}
        result = await self._request(GET_TASK_URL, data, headers)
        if result.get("code") in (CODE_OK_ZERO, CODE_OK_HTTP):
            tasks = (result.get("data") or {}).get("dailyTask", [])
            return tasks if isinstance(tasks, list) else []
        return []

    async def get_forum_list(self) -> list[dict[str, Any]]:
        """Get forum post list for BBS tasks."""
        headers = {
            "token": self.cookie,
            "did": self.did,
        }
        headers["version"] = "2.25"
        data = {
            "pageIndex": "1",
            "pageSize": "20",
            "timeType": "0",
            "searchType": "1",
            "forumId": "9",
            "gameId": "3",
        }
        result = await self._request(FORUM_LIST_URL, data, headers)
        if result.get("code") in (CODE_OK_ZERO, CODE_OK_HTTP):
            posts = (result.get("data") or {}).get("postList", [])
            return posts if isinstance(posts, list) else []
        return []

    async def do_post_detail(self, post_id: str) -> dict[str, Any]:
        """View a post (browse task)."""
        headers = {
            "token": self.cookie,
            "did": self.did,
        }
        data = {
            "postId": post_id,
            "showOrderType": "2",
            "isOnlyPublisher": "0",
        }
        result = await self._request(POST_DETAIL_URL, data, headers)
        return result

    async def do_like(self, post_id: str, to_user_id: str) -> dict[str, Any]:
        """Like a post."""
        headers = {
            "token": self.cookie,
            "did": self.did,
            "b-at": self.bat,
        }
        data = {
            "gameId": "3",
            "likeType": "1",
            "operateType": "1",
            "postId": post_id,
            "toUserId": to_user_id,
        }
        result = await self._request(LIKE_URL, data, headers)
        return result

    async def do_share(self) -> dict[str, Any]:
        """Share a post."""
        headers = {
            "token": self.cookie,
            "did": self.did,
            "b-at": self.bat,
        }
        data = {"gameId": "3"}
        result = await self._request(SHARE_URL, data, headers)
        return result
