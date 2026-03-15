"""
src/bind.py - 绑定逻辑
"""

import asyncio
import re
import aiohttp
from astrbot import logger
from astrbot.api.event import AstrMessageEvent

from .common import (
    get_config, load_binds, save_binds, get_user_binds,
    has_any_bind, mask_id, SERVER_NAME, SERVERS
)

# ───────────────────────── Playwright 校验 ───────────────────────

async def fetch_profile(sekai_id: str, server: str) -> dict | None:
    """请求指定服务器个人页，返回 {"server": "cn", "name": "xxx"} 或 None"""
    cfg          = get_config()
    api_base     = cfg.get("api_base", "").rstrip("/")
    token        = cfg.get("token", "")
    url          = f"{api_base}/profile/{server}/{sekai_id}?token={token}"

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page    = await browser.new_page()
            await page.goto(url, timeout=15000, wait_until="networkidle")
            content = await page.content()
            if "加载失败" in content:
                return None
            name_match = re.search(r'<[^>]*class="[^"]*name[^"]*"[^>]*>([^<]+)<', content)
            name = name_match.group(1).strip() if name_match else "未知"
            return {"server": server, "name": name}
        finally:
            await browser.close()

# ───────────────────────── 格式化 ────────────────────────────────

def format_bind_status(user: dict) -> str:
    default = user.get("default")
    lines   = []
    for s in SERVERS:
        sid    = user.get(s)
        prefix = "@ " if s == default else "     "
        lines.append(f"{prefix}【{SERVER_NAME[s]}】")
        lines.append(mask_id(sid) if sid else "未绑定")
    default_name = SERVER_NAME.get(default, "未设置") if default else "未设置"
    lines.append(f"你的默认服务器为【{default_name}】")
    lines.append("通过' /pjsk服务器 cn|tw|jp '可切换你的默认服务器")
    return "\n".join(lines)

def bind_success_msg(server: str, name: str) -> str:
    return (
        f"{SERVER_NAME[server]}绑定成功: {name}\n"
        f"你的默认服务器已修改为【{SERVER_NAME[server]}】\n"
        f"通过' /pjsk服务器 cn|tw|jp '可切换你的默认服务器"
    )

# ───────────────────────── 指令处理函数 ──────────────────────────

async def handle_bind(event: AstrMessageEvent, sekai_id: str, server: str | None) -> str:
    """
    处理绑定逻辑，返回回复文字
    server=None 表示自动检测三服
    """
    qq    = str(event.get_sender_id())
    binds = load_binds()
    user  = get_user_binds(binds, qq)

    # 无id
    if not sekai_id:
        if server:
            # /cn绑定 无id
            sid = user.get(server)
            if not sid:
                return f"请输入要绑定的 id，例如：/{server}绑定 114514"
            return f"当前绑定的{SERVER_NAME[server]}为：\n{mask_id(sid)}"
        else:
            # /绑定 无id
            if not has_any_bind(user):
                return "请输入要绑定的 id，例如：/绑定 114514"
            return format_bind_status(user)

    # 有id，指定服务器
    if server:
        try:
            result = await fetch_profile(sekai_id, server)
        except Exception as e:
            logger.warning(f"[bind] {server} 请求失败：{e}")
            return "服务器请求失败，请稍后再试"
        if not result:
            return "绑定失败，请检查id是否正确"
        user[server]    = sekai_id
        user["default"] = server
        save_binds(binds)
        return bind_success_msg(server, result["name"])

    # 有id，自动检测三服
    try:
        results = await asyncio.gather(
            *[fetch_profile(sekai_id, s) for s in SERVERS],
            return_exceptions=True
        )
    except Exception as e:
        logger.warning(f"[bind] 并发请求失败：{e}")
        return "服务器请求失败，请稍后再试"

    success = [r for r in results if isinstance(r, dict)]
    if not success:
        return "所有可请求服务器绑定失败，请检查id是否正确！"

    msgs = []
    for r in success:
        s = r["server"]
        user[s]         = sekai_id
        user["default"] = s
        msgs.append(f"{SERVER_NAME[s]}绑定成功: {r['name']}")

    msgs.append(f"你的默认服务器已修改为【{SERVER_NAME[user['default']]}】")
    msgs.append("通过' /pjsk服务器 cn|tw|jp '可切换你的默认服务器")
    save_binds(binds)
    return "\n".join(msgs)

async def handle_switch_server(event: AstrMessageEvent, server: str | None) -> str:
    """处理切换默认服务器"""
    qq    = str(event.get_sender_id())
    binds = load_binds()
    user  = get_user_binds(binds, qq)

    if not server:
        if not has_any_bind(user):
            return "你还没绑定任何账号！"
        return format_bind_status(user)

    if server not in SERVERS:
        return "请输入有效的服务器：cn / tw / jp"
    if not user.get(server):
        return f"你还没有绑定{SERVER_NAME[server]}的账号"

    user["default"] = server
    save_binds(binds)
    return f"已将默认服务器切换为【{SERVER_NAME[server]}】"