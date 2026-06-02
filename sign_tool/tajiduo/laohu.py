from __future__ import annotations

import time
import uuid
import hashlib
from base64 import b64encode
from typing import Any
from dataclasses import field, dataclass

import httpx

from ..log import get_logger
from .constants import (
    LAOHU_BASE_URL,
    LAOHU_APP_ID,
    LAOHU_APP_KEY,
    LAOHU_SDK_VERSION,
    LAOHU_USER_AGENT,
    LAOHU_DEFAULT_PACKAGE,
    LAOHU_DEFAULT_VERSION_CODE,
)

logger = get_logger()


class LaohuError(Exception):
    def __init__(self, message: str, raw: Any = None):
        super().__init__(message)
        self.message = message
        self.raw = raw


def make_device_id() -> str:
    return f"HT{uuid.uuid4().hex[:14].upper()}"


@dataclass
class LaohuDevice:
    device_id: str = ""
    device_type: str = "Pixel 6"
    device_model: str = "Pixel 6"
    device_name: str = "Pixel 6"
    device_sys: str = "Android 14"
    adm: str = ""
    imei: str = ""
    idfa: str = ""
    mac: str = ""

    def __post_init__(self) -> None:
        if not self.device_id:
            self.device_id = make_device_id()
        if not self.adm:
            self.adm = self.device_id


@dataclass(frozen=True)
class LaohuAccount:
    user_id: int
    token: str
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, data: dict) -> LaohuAccount:
        raw_user_id = data.get("userId")
        raw_token = data.get("token")
        if raw_user_id is None or raw_token is None:
            raise LaohuError("老虎登录返回缺少 userId/token", data)
        token = str(raw_token)
        if not token:
            raise LaohuError("老虎登录返回 token 为空", data)
        try:
            user_id = int(raw_user_id)
        except (TypeError, ValueError) as err:
            raise LaohuError("老虎登录返回 userId 格式错误", data) from err
        if user_id <= 0:
            raise LaohuError("老虎登录返回 userId 无效", data)
        return cls(user_id=user_id, token=token, raw=data)


class LaohuClient:
    def __init__(self, device: LaohuDevice | None = None):
        if len(LAOHU_APP_KEY) < 16:
            raise ValueError("app_key 长度必须 >= 16")
        self.device = device if device is not None else LaohuDevice()
        self._aes_key = LAOHU_APP_KEY[-16:].encode()

    def _aes_encrypt(self, plain: str) -> str:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad

        cipher = AES.new(self._aes_key, AES.MODE_ECB)
        return b64encode(cipher.encrypt(pad(plain.encode(), AES.block_size))).decode()

    def _sign(self, params: dict[str, str]) -> str:
        raw = "".join(params[key] for key in sorted(params)) + LAOHU_APP_KEY
        return hashlib.md5(raw.encode()).hexdigest()

    def _common_fields(self, *, use_millis: bool) -> dict[str, str]:
        device = self.device
        ts = int(time.time() * 1000) if use_millis else int(time.time())
        base = {
            "appId": str(LAOHU_APP_ID),
            "channelId": "1",
            "deviceId": device.device_id,
            "deviceType": device.device_type,
            "deviceModel": device.device_model,
            "deviceName": device.device_name,
            "deviceSys": device.device_sys,
            "adm": device.adm,
            "idfa": device.idfa,
            "sdkVersion": LAOHU_SDK_VERSION,
            "bid": LAOHU_DEFAULT_PACKAGE,
            "t": str(ts),
        }
        if use_millis:
            base["version"] = str(LAOHU_DEFAULT_VERSION_CODE)
            base["mac"] = device.mac
        else:
            base["versionCode"] = str(LAOHU_DEFAULT_VERSION_CODE)
            base["imei"] = device.imei
        return base

    async def _submit(
        self,
        path: str,
        params: dict[str, str],
        *,
        keep_empty: bool = False,
    ) -> Any:
        signed = dict(params)
        signed["sign"] = self._sign(signed)
        cleaned = {k: v for k, v in signed.items() if v is not None and (keep_empty or v != "")}

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{LAOHU_BASE_URL}{path}",
                headers={"User-Agent": LAOHU_USER_AGENT},
                data=cleaned,
            )
            if resp.status_code >= 400:
                raise LaohuError(f"HTTP {resp.status_code}: {path}")
            payload = resp.json()

        if payload.get("code") not in (0, "0"):
            raise LaohuError(f"[{path}] {payload.get('message', '')}", payload)
        result = payload.get("result")
        return result if result is not None else {}

    async def send_sms_code(self, cellphone: str) -> None:
        params = self._common_fields(use_millis=False)
        params["cellphone"] = cellphone
        params["areaCodeId"] = "1"
        params["type"] = "16"
        await self._submit("/m/newApi/sendPhoneCaptchaWithOutLogin", params)
        logger.info(f"验证码已发送至 {cellphone}")

    async def check_sms_code(self, cellphone: str, code: str) -> None:
        params = self._common_fields(use_millis=False)
        params["cellphone"] = cellphone
        params["captcha"] = code
        await self._submit("/m/newApi/checkPhoneCaptchaWithOutLogin", params)

    async def login_by_sms(self, cellphone: str, code: str) -> LaohuAccount:
        await self.check_sms_code(cellphone, code)

        params = self._common_fields(use_millis=True)
        params["cellphone"] = self._aes_encrypt(cellphone)
        params["captcha"] = self._aes_encrypt(code)
        params["areaCodeId"] = "1"
        params["type"] = "16"

        result = await self._submit("/openApi/sms/new/login", params, keep_empty=True)
        return LaohuAccount.from_payload(result)
