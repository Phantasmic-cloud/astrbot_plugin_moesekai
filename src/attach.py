"""
src/attach.py - 查询绑定id、用户统计
"""

from astrbot.api.event import AstrMessageEvent
from .common import load_binds, get_user_binds, has_any_bind, SERVER_NAME, SERVERS

# ───────────────────────── 查询绑定id ────────────────────────────

async def handle_query_id(event: AstrMessageEvent, server: str | None) -> str:
    qq    = str(event.get_sender_id())
    binds = load_binds()
    user  = get_user_binds(binds, qq)

    if not has_any_bind(user):
        return "你还没绑定id！"

    if server:
        sekai_id = user.get(server)
        if not sekai_id:
            return f"你还没有绑定{SERVER_NAME[server]}的账号"
        return sekai_id

    # 默认服
    default = user.get("default")
    if not default or not user.get(default):
        return "请先使用 `/pjsk服务器 cn/tw/jp` 设置默认服务器"
    return user[default]

# ───────────────────────── 用户统计 ──────────────────────────────

async def handle_user_stats() -> str:
    binds    = load_binds()
    cn_count = tw_count = jp_count = 0

    for qq, user in binds.items():
        if not isinstance(user, dict):
            continue
        if user.get("cn"): cn_count += 1
        if user.get("tw"): tw_count += 1
        if user.get("jp"): jp_count += 1

    total = cn_count + tw_count + jp_count
    return (
        f"所有群聊统计:\n"
        f"【日服】：{jp_count}\n"
        f"【台服】：{tw_count}\n"
        f"【国服】：{cn_count}\n"
        f"---\n"
        f"【总计】：{total}"
    )