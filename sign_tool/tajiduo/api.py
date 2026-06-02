from __future__ import annotations

import time
import random
import hashlib
from typing import Any
from dataclasses import field, dataclass

import httpx

from ..log import get_logger
from .constants import (
    TAJIDUO_BASE_URL,
    TAJIDUO_USER_CENTER_APP_ID,
    TAJIDUO_APP_VERSION,
    TAJIDUO_CLIENT_UID,
    TAJIDUO_DS_SALT,
    TAJIDUO_DS_NONCE_ALPHABET,
    TAJIDUO_USER_AGENT,
    TAJIDUO_SIGNIN_COMMUNITY_ID,
    YIHUAN_TASK_COMMUNITY_IDS,
    SHARE_PLATFORM_WX_SESSION,
)

logger = get_logger()


class TajiduoError(Exception):
    def __init__(self, message: str, raw: Any = None):
        super().__init__(message)
        self.message = message
        self.raw = raw


@dataclass(frozen=True)
class TajiduoSession:
    access_token: str
    refresh_token: str
    center_uid: str
    raw: dict = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class TajiduoRoleRef:
    role_id: str
    role_name: str
    server_id: str = ""


@dataclass(frozen=True)
class GameRoleList:
    bind_role_id: int = 0
    roles: list[TajiduoRoleRef] = field(default_factory=list)


@dataclass(frozen=True)
class CommunitySignResult:
    exp: int = 0
    gold_coin: int = 0
    raw: dict = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class UserTask:
    task_key: str
    task_name: str
    complete_times: int = 0
    limit_times: int = 1
    finished: bool = False

    @property
    def remaining(self) -> int:
        return max(0, self.limit_times - self.complete_times)


@dataclass(frozen=True)
class UserTasks:
    daily: list[UserTask] = field(default_factory=list)


@dataclass(frozen=True)
class RecommendPost:
    post_id: str
    title: str = ""


@dataclass(frozen=True)
class RecommendPostList:
    posts: list[RecommendPost] = field(default_factory=list)


def _expect_dict(data: Any, msg: str) -> dict:
    if isinstance(data, dict):
        return data
    raise TajiduoError(msg, data)


def _expect_list(data: Any, msg: str) -> list:
    if isinstance(data, list):
        return data
    raise TajiduoError(msg, data)


class TajiduoClient:
    def __init__(
        self,
        device_id: str,
        *,
        access_token: str = "",
        refresh_token: str = "",
        center_uid: str = "",
    ):
        if not device_id:
            raise ValueError("device_id 不能为空")
        self.device_id = device_id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.center_uid = center_uid

    def _default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": TAJIDUO_USER_AGENT,
            "platform": "android",
            "deviceid": self.device_id,
            "appversion": TAJIDUO_APP_VERSION,
            "uid": TAJIDUO_CLIENT_UID,
            "authorization": "",
        }

    def _ds_headers(self) -> dict[str, str]:
        headers = self._default_headers()
        timestamp = str(int(time.time()))
        nonce = "".join(random.choice(TAJIDUO_DS_NONCE_ALPHABET) for _ in range(8))
        raw = f"{timestamp}{nonce}{TAJIDUO_APP_VERSION}{TAJIDUO_DS_SALT}"
        headers["ds"] = f"{timestamp},{nonce},{hashlib.md5(raw.encode()).hexdigest()}"
        return headers

    def _authed_headers(self) -> dict[str, str]:
        if not self.access_token:
            raise TajiduoError("尚未登录塔吉多用户中心")
        headers = self._ds_headers()
        headers["authorization"] = self.access_token
        return headers

    async def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        h = headers or self._ds_headers()
        if body is not None:
            h.setdefault("Content-Type", "application/x-www-form-urlencoded")

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.request(
                method,
                f"{TAJIDUO_BASE_URL}{path}",
                headers=h,
                params=query,
                data=body,
            )
            if resp.status_code >= 400:
                raise TajiduoError(f"HTTP {resp.status_code}: {path}", {"status_code": resp.status_code})
            if not resp.content:
                raise TajiduoError(f"响应为空: {path}")
            payload = resp.json()

        if not isinstance(payload, dict):
            return payload

        code = payload.get("code")
        if code not in (0, "0", 200, "200"):
            raise TajiduoError(f"[{path}] {payload.get('msg', '')}", payload)
        data = payload.get("data")
        return data if data is not None else {}

    # Login methods

    async def user_center_login(self, laohu_token: str, laohu_user_id: str) -> TajiduoSession:
        data = await self._request(
            "/usercenter/api/login",
            method="POST",
            body={
                "token": laohu_token,
                "userIdentity": str(laohu_user_id),
                "appId": TAJIDUO_USER_CENTER_APP_ID,
            },
        )
        access_token = data.get("accessToken")
        refresh_token = data.get("refreshToken")
        center_uid = data.get("uid")
        if access_token is None or refresh_token is None or center_uid is None:
            raise TajiduoError("塔吉多登录返回缺少 accessToken/refreshToken/uid", data)

        self.access_token = str(access_token)
        self.refresh_token = str(refresh_token)
        self.center_uid = str(center_uid)
        return TajiduoSession(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            center_uid=self.center_uid,
            raw=data,
        )

    async def refresh_session(self) -> TajiduoSession:
        if not self.refresh_token:
            raise TajiduoError("refresh_token 为空，无法续期")
        headers = self._ds_headers()
        headers["authorization"] = self.refresh_token
        data = await self._request(
            "/usercenter/api/refreshToken",
            method="POST",
            headers=headers,
        )
        access_token = data.get("accessToken")
        new_refresh = data.get("refreshToken")
        if access_token is None or new_refresh is None:
            raise TajiduoError("refreshToken 未下发 accessToken/refreshToken", data)
        self.access_token = str(access_token)
        self.refresh_token = str(new_refresh)
        return TajiduoSession(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            center_uid=self.center_uid,
            raw=data,
        )

    # Game role methods

    async def get_game_roles(self, game_id: str) -> GameRoleList:
        data = await self._request(
            "/usercenter/api/v2/getGameRoles",
            method="GET",
            query={"gameId": game_id},
            headers=self._authed_headers(),
        )
        if isinstance(data, list):
            roles = [TajiduoRoleRef(
                role_id=str(r.get("roleId", "")),
                role_name=str(r.get("roleName", "")),
                server_id=str(r.get("serverId", "")),
            ) for r in data if isinstance(r, dict)]
            return GameRoleList(roles=roles)
        if isinstance(data, dict):
            bind = data.get("bindRole", 0)
            raw_roles = data.get("roles", [])
            roles = [TajiduoRoleRef(
                role_id=str(r.get("roleId", "")),
                role_name=str(r.get("roleName", "")),
                server_id=str(r.get("serverId", "")),
            ) for r in raw_roles if isinstance(r, dict)]
            return GameRoleList(bind_role_id=bind, roles=roles)
        return GameRoleList()

    # Sign methods

    async def get_community_sign_state(self, community_id: str) -> bool:
        data = await self._request(
            "/apihub/api/getSignState",
            method="GET",
            query={"communityId": community_id},
            headers=self._authed_headers(),
        )
        return bool(data)

    async def app_signin(self, community_id: str = TAJIDUO_SIGNIN_COMMUNITY_ID) -> CommunitySignResult:
        data = await self._request(
            "/apihub/api/signin",
            method="POST",
            body={"communityId": community_id},
            headers=self._authed_headers(),
        )
        d = _expect_dict(data, "App签到返回格式错误")
        return CommunitySignResult(
            exp=int(d.get("exp", 0)),
            gold_coin=int(d.get("gold_coin", 0)),
            raw=d,
        )

    async def game_signin(self, role_id: str, game_id: str) -> dict:
        data = await self._request(
            "/apihub/awapi/sign",
            method="POST",
            body={"roleId": role_id, "gameId": game_id},
            headers=self._authed_headers(),
        )
        return _expect_dict(data, "游戏签到返回格式错误")

    # Task methods

    async def get_user_tasks(self) -> UserTasks:
        data = await self._request(
            "/apihub/api/getUserTasks",
            method="GET",
            query={"gid": "1"},
            headers=self._authed_headers(),
        )
        d = _expect_dict(data, "任务列表格式错误")
        daily = []
        for t in d.get("task_list1", []):
            if not isinstance(t, dict):
                continue
            daily.append(UserTask(
                task_key=str(t.get("taskKey", "")),
                task_name=str(t.get("taskName", "")),
                complete_times=int(t.get("completeTimes", 0)),
                limit_times=int(t.get("limitTimes", 1)),
                finished=bool(t.get("finished", False)),
            ))
        return UserTasks(daily=daily)

    async def list_recommend_posts(self, community_id: str, page: int = 1) -> RecommendPostList:
        data = await self._request(
            "/bbs/api/getRecommendPostList",
            method="GET",
            query={
                "communityId": community_id,
                "page": str(page),
                "count": "20",
                "version": "0",
            },
            headers=self._authed_headers(),
        )
        d = _expect_dict(data, "推荐帖子列表格式错误")
        posts = []
        for p in d.get("posts", []):
            if isinstance(p, dict) and p.get("postId"):
                posts.append(RecommendPost(
                    post_id=str(p["postId"]),
                    title=str(p.get("title", "")),
                ))
        return RecommendPostList(posts=posts)

    async def view_post(self, post_id: str) -> dict:
        data = await self._request(
            "/bbs/api/getPostFull",
            method="GET",
            query={"postId": post_id},
            headers=self._authed_headers(),
        )
        return _expect_dict(data, "浏览帖子返回格式错误")

    async def like_post(self, post_id: str) -> bool:
        data = await self._request(
            "/bbs/api/post/like",
            method="POST",
            body={"postId": post_id},
            headers=self._authed_headers(),
        )
        return bool(data)

    async def share_post(self, post_id: str, platform: str = SHARE_PLATFORM_WX_SESSION) -> None:
        await self._request(
            "/bbs/api/post/share",
            method="POST",
            body={"postId": post_id, "platform": platform},
            headers=self._authed_headers(),
        )
