"""Server-side Australia Post testbed adapter with safe fallbacks and caching."""

import os
import time
from collections import deque
from datetime import datetime, timezone
from threading import Lock

import httpx

from .models import Shipment

TESTBED_URL = "https://digitalapi.auspost.com.au/test/shipping/v1/track"


def unavailable(message: str, state: str = "unavailable") -> dict:
    return {"state": state, "status": None, "last_update": None, "events": [], "message": message,
            "environment": "testbed", "checked_at": datetime.now(timezone.utc).isoformat()}


def text(value) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def event_time(event: dict) -> float:
    if not isinstance(event.get("date"), str):
        return float("-inf")
    try:
        stamp = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
        return stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).timestamp()
    except (ValueError, TypeError, KeyError, OverflowError):
        return float("-inf")


def parse_tracking(payload, tracking_no: str) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("tracking_results"), list):
        return unavailable("承运商返回的数据格式无效")
    result = next((r for r in payload["tracking_results"] if isinstance(r, dict) and r.get("tracking_id") == tracking_no), None)
    if result is None:
        return unavailable("承运商未返回该运单的记录")
    if result.get("errors"):
        return unavailable("承运商返回查询错误，该运单目前不可查询")
    items = result.get("trackable_items", [])
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        return unavailable("承运商返回的数据格式无效")
    events, statuses = [], []
    if text(result.get("status")):
        statuses.append(result["status"])
    for item in items:
        if item.get("errors"):
            return unavailable("承运商返回部分包裹错误，物流结果不完整")
        if text(item.get("status")):
            statuses.append(item["status"])
        raw_events = item.get("events", [])
        if not isinstance(raw_events, list):
            return unavailable("承运商返回的数据格式无效")
        for event in raw_events:
            if not isinstance(event, dict):
                return unavailable("承运商返回的数据格式无效")
            description, date = text(event.get("description")), text(event.get("date"))
            if description or date:
                events.append({"description": description or "承运商未提供事件描述", "date": date,
                               "location": text(event.get("location")), "article_id": text(item.get("article_id"))})
    events.sort(key=event_time, reverse=True)
    if not events and not statuses:
        return unavailable("承运商尚未提供物流状态或事件")
    return {**unavailable("测试环境返回，仅用于集成验证"), "state": "available",
            "status": " / ".join(dict.fromkeys(statuses)) or None,
            "last_update": next((event["date"] for event in events if event_time(event) != float("-inf")), None), "events": events}


class TrackingService:
    def __init__(self):
        self.cache: dict[tuple[str, str], tuple[float, dict]] = {}
        self.requests: deque[float] = deque()
        self.lock = Lock()

    def get(self, shipment: Shipment) -> dict:
        if shipment.carrier == "tnt":
            return {**unavailable("本轮尚未实现 TNT 集成，相关运费为 A$0.00", "not_implemented"), "environment": None}
        key = (shipment.carrier, shipment.tracking_no)
        with self.lock:
            now = time.monotonic()
            if key in self.cache and now - self.cache[key][0] < 60:
                return {**self.cache[key][1], "cached": True}
            api_key, password = os.getenv("AUSPOST_API_KEY"), os.getenv("AUSPOST_API_PASSWORD")
            account = os.getenv("STARTRACK_ACCOUNT_NUMBER" if shipment.carrier == "startrack" else "AUSPOST_ACCOUNT_NUMBER")
            if not api_key or not password or not account:
                return unavailable("服务端尚未配置承运商凭证", "not_configured")
            while self.requests and now - self.requests[0] >= 60:
                self.requests.popleft()
            if len(self.requests) >= 10:
                return unavailable("已达到每分钟查询上限，请稍后再试")
            self.requests.append(now)
            try:
                response = httpx.get(TESTBED_URL, params={"tracking_ids": shipment.tracking_no},
                                     auth=(api_key, password), headers={"Account-Number": account, "Accept": "application/json"},
                                     timeout=10, follow_redirects=False)
                if response.status_code in (401, 403):
                    result = unavailable(f"承运商测试接口返回 HTTP {response.status_code}：认证或账户授权失败")
                elif response.status_code != 200:
                    result = unavailable(f"承运商接口返回 HTTP {response.status_code}，请稍后重试")
                else:
                    result = parse_tracking(response.json(), shipment.tracking_no)
            except httpx.TimeoutException:
                result = unavailable("承运商接口查询超时，请稍后重试")
            except (httpx.HTTPError, ValueError):
                result = unavailable("承运商接口连接失败或响应不是有效 JSON")
            self.cache = {k: v for k, v in self.cache.items() if now - v[0] < 60}
            self.cache[key] = (time.monotonic(), result)
            return {**result, "cached": False}
