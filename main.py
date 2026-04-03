"""
astrbot_plugin_moesekai/main.py - 插件入口
"""

import asyncio
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event.filter import PermissionType, EventMessageType
from astrbot.api import AstrBotConfig, logger
import astrbot.api.message_components as Comp

from .src.common import set_config, is_group_enabled, set_group_enabled, SERVER_NAME
from .src.asset import start_asset_loop
from .src.sk_forecast import start_forecast_loop, handle_forecast


async def _send_forecast(event, server):
    """处理预测线发送，自动判断文字/图片模式"""
    import tempfile, os
    result = await handle_forecast(event, server)
    if isinstance(result, tuple) and result[0] == "image":
        img_bytes = result[1]
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(img_bytes)
            tmp_path = f.name
        return event.chain_result([Comp.Image.fromFileSystem(tmp_path)])
    return event.plain_result(result)


@register(
    "astrbot_plugin_moesekai",
    "Phantasmic",
    "Project Sekai 榜线与预测线查询（Moesekai）",
    "1.3.0",
)
class MoesekaiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        set_config(dict(config))

    async def initialize(self):
        if not getattr(MoesekaiPlugin, "_loops_started", False):
            MoesekaiPlugin._loops_started = True
            asyncio.create_task(start_asset_loop())
            asyncio.create_task(start_forecast_loop())

    async def terminate(self):
        pass

    # ───────────────────────── 工具方法 ──────────────────────────

    def _check_group(self, event: AstrMessageEvent) -> bool:
        gid = event.get_group_id()
        if not gid:
            return True
        return is_group_enabled(str(gid))

    def _get_cmd_and_args(self, event: AstrMessageEvent) -> tuple[str, str]:
        msg = event.message_str.strip()
        if msg.startswith("/"):
            msg = msg[1:]
        return msg.lower(), msg.split(None, 1)[1].strip() if len(msg.split(None, 1)) > 1 else ""

    def _match_cmd(self, full_msg: str, cmd: str) -> bool:
        cmd = cmd.lower()
        return full_msg == cmd or full_msg.startswith(cmd + " ")

    def _check_cmd(self, event: AstrMessageEvent, *cmds: str) -> bool:
        from .src.common import get_config
        require_slash = get_config().get("require_slash", True)
        if require_slash and not event.is_at_or_wake_command:
            return False
        full_msg, _ = self._get_cmd_and_args(event)
        return any(self._match_cmd(full_msg, c) for c in cmds)

    # ───────────────────────── 消息监听 ──────────────────────────

    @filter.event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        is_admin = event.is_admin()

        # ── 群开关管理（不受群开关限制）──
        if self._check_cmd(event, "moesekai on"):
            if not is_admin: return
            gid = event.get_group_id()
            if not gid:
                yield event.plain_result("请在群聊中使用此指令")
                return
            set_group_enabled(str(gid), True)
            yield event.plain_result("已开启本群的 moesekai 服务")
            return

        if self._check_cmd(event, "moesekai off"):
            if not is_admin: return
            gid = event.get_group_id()
            if not gid:
                yield event.plain_result("请在群聊中使用此指令")
                return
            set_group_enabled(str(gid), False)
            yield event.plain_result("已关闭本群的 moesekai 服务")
            return

        if self._check_cmd(event, "moesekai status"):
            if not is_admin: return
            gid = event.get_group_id()
            if not gid:
                yield event.plain_result("请在群聊中使用此指令")
                return
            status = "开启中" if is_group_enabled(str(gid)) else "关闭中"
            yield event.plain_result(f"本群 moesekai 服务：{status}")
            return

        # 以下指令都需要群已开启
        if not self._check_group(event):
            return

        # ── 预测线 ──
        if self._check_cmd(event, "skp", "sk预测", "榜线预测"):
            yield (await _send_forecast(event, "cn"))
            return

        if self._check_cmd(event, "cnskp"):
            yield (await _send_forecast(event, "cn"))
            return

        if self._check_cmd(event, "jpskp"):
            yield (await _send_forecast(event, "jp"))
            return

        if self._check_cmd(event, "twskp"):
            yield event.plain_result("暂不支持台服的预测")
            return
