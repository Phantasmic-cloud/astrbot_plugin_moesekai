"""
src/profile.py - 个人信息截图逻辑
"""

import asyncio
from pathlib import Path
from astrbot import logger

from .common import get_config, load_binds, get_user_binds, has_any_bind, SERVER_NAME

# ───────────────────────── 截图逻辑 ──────────────────────────────

async def screenshot_profile(sekai_id: str, server: str) -> Path:
    cfg      = get_config()
    api_base = cfg.get("api_base", "").rstrip("/")
    token    = cfg.get("token", "")
    delay    = cfg.get("screenshot_delay", 5)
    url      = f"{api_base}/profile/{server}/{sekai_id}?token={token}"
    tmp_path = Path(f"/tmp/moesekai_profile_{server}_{sekai_id}.png")

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page(viewport={"width": 1000, "height": 1446})
            await page.goto(url, timeout=20000, wait_until="networkidle")
            await asyncio.sleep(delay)
            await page.screenshot(
                path=str(tmp_path),
                clip={"x": 0, "y": 0, "width": 1000, "height": 1446}
            )
        finally:
            await browser.close()

    return tmp_path

# ───────────────────────── 指令处理函数 ──────────────────────────

async def handle_profile(event, server: str | None) -> tuple[str | None, Path | None]:
    """
    处理个人信息截图
    返回 (错误文字, None) 或 (None, 图片路径)
    """
    from astrbot.api.event import AstrMessageEvent
    qq    = str(event.get_sender_id())
    binds = load_binds()
    user  = get_user_binds(binds, qq)

    if not has_any_bind(user):
        return "你还没绑定id！", None

    # 确定服务器
    if server:
        target_server = server
        sekai_id      = user.get(server)
        if not sekai_id:
            return f"你还没有绑定{SERVER_NAME[server]}的账号", None
    else:
        target_server = user.get("default")
        if not target_server or not user.get(target_server):
            return "请先使用 `/pjsk服务器 cn/tw/jp` 设置默认服务器", None
        sekai_id = user[target_server]

    try:
        tmp_path = await screenshot_profile(sekai_id, target_server)
        return None, tmp_path
    except Exception as e:
        logger.warning(f"[profile] 截图失败：{e}")
        return "服务器请求失败，请稍后再试", None