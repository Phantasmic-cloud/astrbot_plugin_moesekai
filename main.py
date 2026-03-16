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
from .src.bind import handle_bind, handle_switch_server
from .src.profile import handle_profile
from .src.attach import handle_query_id, handle_user_stats


@register(
    "astrbot_plugin_moesekai",
    "Phantasmic",
    "Project Sekai 玩家数据查询服务（Moesekai）",
    "1.1.0",
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
        """
        提取指令名和参数，自动去掉开头的 /
        返回 (full_msg_no_slash, first_word)
        """
        msg = event.message_str.strip()
        if msg.startswith("/"):
            msg = msg[1:]
        return msg.lower(), msg.split(None, 1)[1].strip() if len(msg.split(None, 1)) > 1 else ""

    def _match_cmd(self, full_msg: str, cmd: str) -> bool:
        """检查消息是否匹配指令（支持多词指令如 moesekai on）"""
        cmd = cmd.lower()
        return full_msg == cmd or full_msg.startswith(cmd + " ")

    def _extract_args(self, full_msg: str, cmd: str) -> str:
        """提取指令后的参数"""
        cmd = cmd.lower()
        if full_msg.startswith(cmd + " "):
            return full_msg[len(cmd):].strip()
        return ""

    def _check_cmd(self, event: AstrMessageEvent, *cmds: str) -> bool:
        """
        检查消息是否匹配指定指令（支持多个别名）
        require_slash=True：只响应通过唤醒词触发的消息（即带/的）
        require_slash=False：所有消息都响应
        """
        from .src.common import get_config
        require_slash = get_config().get("require_slash", True)
        if require_slash and not event.is_at_or_wake_command:
            return False
        full_msg, _ = self._get_cmd_and_args(event)
        return any(self._match_cmd(full_msg, c) for c in cmds)

    def _get_args(self, event: AstrMessageEvent, cmd: str = "") -> str:
        full_msg, _ = self._get_cmd_and_args(event)
        if cmd:
            return self._extract_args(full_msg, cmd)
        parts = full_msg.split(None, 1)
        return parts[1].strip() if len(parts) > 1 else ""

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

        # ── 绑定 ──
        if self._check_cmd(event, "绑定", "bind"):
            yield event.plain_result(await handle_bind(event, self._get_args(event), None))
            return

        if self._check_cmd(event, "cn绑定"):
            yield event.plain_result(await handle_bind(event, self._get_args(event), "cn"))
            return

        if self._check_cmd(event, "tw绑定"):
            yield event.plain_result(await handle_bind(event, self._get_args(event), "tw"))
            return

        if self._check_cmd(event, "jp绑定"):
            yield event.plain_result(await handle_bind(event, self._get_args(event), "jp"))
            return

        if self._check_cmd(event, "pjsk服务器"):
            server = self._get_args(event).lower() or None
            yield event.plain_result(await handle_switch_server(event, server))
            return

        # ── 个人信息 ──
        if self._check_cmd(event, "个人信息"):
            err, path = await handle_profile(event, None)
            if err:
                yield event.plain_result(err)
            else:
                try:
                    yield event.chain_result([Comp.Image.fromFileSystem(str(path))])
                finally:
                    if path:
                        try: path.unlink(missing_ok=True)
                        except: pass
            return

        if self._check_cmd(event, "cn个人信息"):
            err, path = await handle_profile(event, "cn")
            if err:
                yield event.plain_result(err)
            else:
                try:
                    yield event.chain_result([Comp.Image.fromFileSystem(str(path))])
                finally:
                    if path:
                        try: path.unlink(missing_ok=True)
                        except: pass
            return

        if self._check_cmd(event, "tw个人信息"):
            err, path = await handle_profile(event, "tw")
            if err:
                yield event.plain_result(err)
            else:
                try:
                    yield event.chain_result([Comp.Image.fromFileSystem(str(path))])
                finally:
                    if path:
                        try: path.unlink(missing_ok=True)
                        except: pass
            return

        if self._check_cmd(event, "jp个人信息"):
            err, path = await handle_profile(event, "jp")
            if err:
                yield event.plain_result(err)
            else:
                try:
                    yield event.chain_result([Comp.Image.fromFileSystem(str(path))])
                finally:
                    if path:
                        try: path.unlink(missing_ok=True)
                        except: pass
            return

        # ── 查询id ──
        if self._check_cmd(event, "id"):
            yield event.plain_result(await handle_query_id(event, None))
            return

        if self._check_cmd(event, "cnid"):
            yield event.plain_result(await handle_query_id(event, "cn"))
            return

        if self._check_cmd(event, "twid"):
            yield event.plain_result(await handle_query_id(event, "tw"))
            return

        if self._check_cmd(event, "jpid"):
            yield event.plain_result(await handle_query_id(event, "jp"))
            return

        # ── 预测线 ──
        if self._check_cmd(event, "skp", "sk预测", "榜线预测"):
            yield event.plain_result(await handle_forecast(event, None))
            return

        if self._check_cmd(event, "cnskp"):
            yield event.plain_result(await handle_forecast(event, "cn"))
            return

        if self._check_cmd(event, "jpskp"):
            yield event.plain_result(await handle_forecast(event, "jp"))
            return

        if self._check_cmd(event, "twskp"):
            yield event.plain_result("暂不支持台服的预测")
            return

        # ── 用户统计 ──
        if self._check_cmd(event, "用户统计"):
            if not is_admin: return
            yield event.plain_result(await handle_user_stats())
            return
