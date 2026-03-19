"""
src/sk_forecast.py - 预测线查询
"""

import asyncio
import aiohttp
import json
from datetime import datetime, timezone
from pathlib import Path
from astrbot import logger

from .common import get_config, load_binds, get_user_binds, has_any_bind, SERVER_NAME
from .asset import get_current_event

# ───────────────────────── 路径工具 ──────────────────────────────

def _forecast_path(region: str) -> Path:
    from .common import data_dir
    return data_dir() / f"forecast_{region}.json"

# ───────────────────────── 缓存读写 ──────────────────────────────

def _save_forecast(region: str, data: dict):
    path = _forecast_path(region)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def _load_forecast(region: str) -> dict | None:
    path = _forecast_path(region)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text("utf-8"))
    except Exception as e:
        logger.warning(f"[sk_forecast] 读取 {region} 缓存失败：{e}")
        return None

# ───────────────────────── 数据请求 ──────────────────────────────

async def _fetch_forecast(region: str) -> bool:
    cfg      = get_config()
    url_tpl  = cfg.get("forecast_url", "")
    ranks    = cfg.get("forecast_ranks", [50, 100, 200, 300, 500, 1000, 2000, 3000, 5000, 10000, 50000])

    event = get_current_event(region)
    if not event:
        logger.warning(f"[sk_forecast] {region} 找不到当前活动")
        return False

    event_id      = event["id"]
    region_prefix = "" if region == "cn" else f"{region}/"
    url           = url_tpl.replace("{region}", region_prefix).replace("{event_id}", str(event_id))

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    logger.warning(f"[sk_forecast] {region} 请求返回 {resp.status}")
                    return False
                raw_text = await resp.text()
                remote   = json.loads(raw_text)
    except Exception as e:
        logger.warning(f"[sk_forecast] {region} 请求失败：{e}")
        return False

    fetch_time    = datetime.now(tz=timezone.utc).isoformat()
    ts_ms         = remote.get("timestamp")
    old_cache     = _load_forecast(region)
    old_pred_time = old_cache.get("predict_time") if old_cache else None
    new_pred_time = ts_ms if ts_ms else fetch_time

    _save_forecast(region, {
        "event_id":    event_id,
        "event_name":  event.get("name", ""),
        "fetch_time":  fetch_time,
        "predict_time": new_pred_time if new_pred_time != old_pred_time else (old_pred_time or fetch_time),
        "ranks":       ranks,
        "data":        remote,
    })

    logger.info(f"[sk_forecast] {region} 预测线数据已更新 (event_id={event_id})")
    return True

# ───────────────────────── 定时任务 ──────────────────────────────

async def _do_forecast_update():
    """执行一次预测线更新"""
    cfg     = get_config()
    regions = cfg.get("forecast_regions", ["cn", "jp"])
    retry   = cfg.get("forecast_error_retry", 10) * 60

    logger.info("[sk_forecast] 开始更新预测线数据...")
    for region in regions:
        ok = await _fetch_forecast(region)
        if not ok:
            logger.warning(f"[sk_forecast] {region} 请求失败，{cfg.get('forecast_error_retry', 10)} 分钟后重试")
            await asyncio.sleep(retry)
            await _fetch_forecast(region)

async def start_forecast_loop():
    cfg     = get_config()
    enabled = cfg.get("forecast_enabled", True)
    if not enabled:
        logger.info("[sk_forecast] 预测线功能已关闭")
        return

    interval = cfg.get("forecast_update_interval", 10) * 60

    # 启动时立即请求一次
    logger.info("[sk_forecast] 启动时请求预测线数据...")
    await _do_forecast_update()

    # 之后严格按间隔定时执行
    while True:
        await asyncio.sleep(interval)
        await _do_forecast_update()

# ───────────────────────── 格式化输出 ────────────────────────────

def _fmt_time_ago(time_val) -> str:
    try:
        now = datetime.now(tz=timezone.utc)
        if isinstance(time_val, (int, float)):
            dt = datetime.fromtimestamp(time_val / 1000, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(time_val).replace("Z", "+00:00"))
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
        minutes = int((now - dt).total_seconds() / 60)
        return "刚刚" if minutes < 1 else f"{minutes}分钟前"
    except Exception:
        return "未知"

def _fmt_score(score) -> str:
    try:
        return f"{float(score) / 10000:.4f}w"
    except Exception:
        return "-"

def build_forecast_msg(region: str, cache: dict) -> str:
    cfg        = get_config()
    ranks      = cfg.get("forecast_ranks", [50, 100, 200, 300, 500, 1000, 2000, 3000, 5000, 10000, 50000])
    event_id   = cache.get("event_id", "?")
    event_name = cache.get("event_name", "")
    fetch_time = _fmt_time_ago(cache.get("fetch_time", ""))
    pred_time  = _fmt_time_ago(cache.get("predict_time", ""))
    charts     = (cache.get("data") or {}).get("data", {}).get("charts", [])
    rank_map   = {item["Rank"]: item.get("PredictedScore") for item in charts if "Rank" in item}

    lines = [
        f"当前活动({region.upper()})：第{event_id}期",
        event_name,
        "----------------",
    ]
    for rank in ranks:
        score = rank_map.get(rank)
        if score is None or float(score) == 0:
            continue
        lines.append(f"{rank}位: {_fmt_score(score)}")

    lines += [
        "----------------",
        f"预测时间: {pred_time}",
        f"获取时间: {fetch_time}",
        "数据来源: pjsk.moe(by 東雪)",
        "From Phantasmic(郁郁葱葱)",
    ]
    return "\n".join(lines)

# ───────────────────────── 指令处理函数 ──────────────────────────

async def handle_forecast(event, server: str | None) -> str:
    cfg              = get_config()
    forecast_regions = cfg.get("forecast_regions", ["cn", "jp"])

    # 确定服务器
    if server:
        target = server
    else:
        qq    = str(event.get_sender_id())
        binds = load_binds()
        user  = get_user_binds(binds, qq)
        if not has_any_bind(user):
            return "你还没绑定id！"
        target = user.get("default")
        if not target or not user.get(target):
            return "请先使用 `/pjsk服务器 cn/tw/jp` 设置默认服务器"

    if target not in forecast_regions:
        return f"暂不支持{SERVER_NAME.get(target, target)}的预测"

    current_event = get_current_event(target)
    if not current_event:
        return f"{SERVER_NAME.get(target, target)}当前没有进行中的活动"

    cache = _load_forecast(target)
    if not cache:
        return f"{SERVER_NAME.get(target, target)}预测线数据暂未就绪，请稍后再试"

    if cache.get("event_id") != current_event.get("id"):
        return f"{SERVER_NAME.get(target, target)}预测线数据更新中，请稍后再试"

    return build_forecast_msg(target, cache)
