"""
src/asset.py - MasterData 资产爬取
"""

import asyncio
import json
import aiohttp
from pathlib import Path
from datetime import datetime, timezone
from astrbot import logger

from .common import get_config, data_dir

# ───────────────────────── 路径工具 ──────────────────────────────

def _local_path(region: str) -> Path:
    return data_dir() / f"events_{region}.json"

# ───────────────────────── 爬取逻辑 ──────────────────────────────

async def _fetch_text(url: str) -> str | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    return await resp.text()
                logger.warning(f"[asset] 请求 {url} 返回状态码 {resp.status}")
                return None
    except Exception as e:
        logger.warning(f"[asset] 请求失败：{e}")
        return None

async def _check_and_update(region: str, base_url: str) -> bool:
    url        = f"{base_url.rstrip('/')}/events.json"
    local_path = _local_path(region)

    remote_text = await _fetch_text(url)
    if remote_text is None:
        return False

    if local_path.exists():
        if local_path.read_text("utf-8") == remote_text:
            logger.debug(f"[asset] {region} events.json 无更新，跳过")
            return True

    try:
        json.loads(remote_text)
    except Exception as e:
        logger.warning(f"[asset] {region} events.json JSON 解析失败：{e}")
        return False

    local_path.write_text(remote_text, "utf-8")
    logger.info(f"[asset] {region} events.json 已更新")
    return True

async def _check_all_with_retry():
    cfg       = get_config()
    max_retry = cfg.get("masterdata_fetch_max_retry", 3)
    urls      = {
        "cn": cfg.get("masterdata_url_cn", ""),
        "jp": cfg.get("masterdata_url_jp", ""),
    }

    for region, base_url in urls.items():
        if not base_url:
            continue
        for attempt in range(1, max_retry + 1):
            ok = await _check_and_update(region, base_url)
            if ok:
                break
            logger.warning(f"[asset] {region} 第 {attempt}/{max_retry} 次检查失败，{'重试中...' if attempt < max_retry else '已达最大重试次数'}")
            if attempt < max_retry:
                await asyncio.sleep(5)

# ───────────────────────── 定时任务 ──────────────────────────────

async def start_asset_loop():
    cfg      = get_config()
    interval = cfg.get("masterdata_fetch_interval", 60) * 60

    logger.info("[asset] 启动时检查 MasterData 更新...")
    await _check_all_with_retry()

    while True:
        await asyncio.sleep(interval)
        logger.info("[asset] 开始检查 MasterData 更新...")
        await _check_all_with_retry()

# ───────────────────────── 对外接口 ──────────────────────────────

def get_current_event(region: str) -> dict | None:
    local_path = _local_path(region)
    if not local_path.exists():
        logger.warning(f"[asset] {region} events.json 不存在")
        return None
    try:
        events = json.loads(local_path.read_text("utf-8"))
    except Exception as e:
        logger.warning(f"[asset] {region} events.json 读取失败：{e}")
        return None

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    for event in events:
        if event.get("startAt", 0) <= now_ms <= event.get("closedAt", 0):
            return event
    return None
