"""
astrbot_plugin_moesekai/main.py - 插件入口
"""

import asyncio
from astrbot.api.star import Context, Star, register
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.event.filter import PermissionType
from astrbot.api import AstrBotConfig, logger
import astrbot.api.message_components as Comp

from src.common import set_config, is_group_enabled, set_group_enabled, SERVER_NAME
from src.asset import start_asset_loop
from src.sk_forecast import start_forecast_loop, handle_forecast
from src.bind import handle_bind, handle_switch_server
from src.profile import handle_profile
from src.attach import handle_query_id, handle_user_stats


@register(
    "astrbot_plugin_moesekai",
    "Phantasmic",
    "Project Sekai 玩家数据查询服务（Moesekai）",
    "1.0.0",
)
class MoesekaiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        set_config(dict(config))

    async def initialize(self):
        # 启动后台定时任务
        asyncio.create_task(start_asset_loop())
        asyncio.create_task(start_forecast_loop())

    async def terminate(self):
        pass

    # ───────────────────────── 群开关检查 ────────────────────────

    def _check_group(self, event: AstrMessageEvent) -> bool:
        """检查群是否已开启 moesekai，私聊直接通过"""
        gid = event.get_group_id()
        if not gid:
            return True
        return is_group_enabled(str(gid))

    # ───────────────────────── 群开关指令 ────────────────────────

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("moesekai on")
    async def cmd_on(self, event: AstrMessageEvent):
        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("请在群聊中使用此指令")
            return
        set_group_enabled(str(gid), True)
        yield event.plain_result("已开启本群的 moesekai 服务")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("moesekai off")
    async def cmd_off(self, event: AstrMessageEvent):
        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("请在群聊中使用此指令")
            return
        set_group_enabled(str(gid), False)
        yield event.plain_result("已关闭本群的 moesekai 服务")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("moesekai status")
    async def cmd_status(self, event: AstrMessageEvent):
        gid = event.get_group_id()
        if not gid:
            yield event.plain_result("请在群聊中使用此指令")
            return
        status = "开启中" if is_group_enabled(str(gid)) else "关闭中"
        yield event.plain_result(f"本群 moesekai 服务：{status}")

    # ───────────────────────── 绑定指令 ──────────────────────────

    @filter.command("绑定", alias={"bind"})
    async def cmd_bind(self, event: AstrMessageEvent, message: str = ""):
        if not self._check_group(event): return
        sekai_id = message.strip()
        result   = await handle_bind(event, sekai_id, None)
        yield event.plain_result(result)

    @filter.command("cn绑定")
    async def cmd_cn_bind(self, event: AstrMessageEvent, message: str = ""):
        if not self._check_group(event): return
        result = await handle_bind(event, message.strip(), "cn")
        yield event.plain_result(result)

    @filter.command("tw绑定")
    async def cmd_tw_bind(self, event: AstrMessageEvent, message: str = ""):
        if not self._check_group(event): return
        result = await handle_bind(event, message.strip(), "tw")
        yield event.plain_result(result)

    @filter.command("jp绑定")
    async def cmd_jp_bind(self, event: AstrMessageEvent, message: str = ""):
        if not self._check_group(event): return
        result = await handle_bind(event, message.strip(), "jp")
        yield event.plain_result(result)

    @filter.command("pjsk服务器")
    async def cmd_server(self, event: AstrMessageEvent, message: str = ""):
        if not self._check_group(event): return
        server = message.strip().lower() or None
        result = await handle_switch_server(event, server)
        yield event.plain_result(result)

    # ───────────────────────── 个人信息 ──────────────────────────

    @filter.command("个人信息")
    async def cmd_profile(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        err, path = await handle_profile(event, None)
        if err:
            yield event.plain_result(err)
            return
        try:
            yield event.chain_result([Comp.Image.fromFileSystem(str(path))])
        finally:
            if path:
                try: path.unlink(missing_ok=True)
                except: pass

    @filter.command("cn个人信息")
    async def cmd_cn_profile(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        err, path = await handle_profile(event, "cn")
        if err:
            yield event.plain_result(err)
            return
        try:
            yield event.chain_result([Comp.Image.fromFileSystem(str(path))])
        finally:
            if path:
                try: path.unlink(missing_ok=True)
                except: pass

    @filter.command("tw个人信息")
    async def cmd_tw_profile(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        err, path = await handle_profile(event, "tw")
        if err:
            yield event.plain_result(err)
            return
        try:
            yield event.chain_result([Comp.Image.fromFileSystem(str(path))])
        finally:
            if path:
                try: path.unlink(missing_ok=True)
                except: pass

    @filter.command("jp个人信息")
    async def cmd_jp_profile(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        err, path = await handle_profile(event, "jp")
        if err:
            yield event.plain_result(err)
            return
        try:
            yield event.chain_result([Comp.Image.fromFileSystem(str(path))])
        finally:
            if path:
                try: path.unlink(missing_ok=True)
                except: pass

    # ───────────────────────── 查询id ────────────────────────────

    @filter.command("id")
    async def cmd_id(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        yield event.plain_result(await handle_query_id(event, None))

    @filter.command("cnid")
    async def cmd_cnid(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        yield event.plain_result(await handle_query_id(event, "cn"))

    @filter.command("twid")
    async def cmd_twid(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        yield event.plain_result(await handle_query_id(event, "tw"))

    @filter.command("jpid")
    async def cmd_jpid(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        yield event.plain_result(await handle_query_id(event, "jp"))

    # ───────────────────────── 预测线 ────────────────────────────

    @filter.command("skp", alias={"sk预测", "榜线预测"})
    async def cmd_skp(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        yield event.plain_result(await handle_forecast(event, None))

    @filter.command("cnskp")
    async def cmd_cnskp(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        yield event.plain_result(await handle_forecast(event, "cn"))

    @filter.command("jpskp")
    async def cmd_jpskp(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        yield event.plain_result(await handle_forecast(event, "jp"))

    @filter.command("twskp")
    async def cmd_twskp(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        yield event.plain_result("暂不支持台服的预测")

    # ───────────────────────── 用户统计 ──────────────────────────

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("用户统计")
    async def cmd_stats(self, event: AstrMessageEvent):
        if not self._check_group(event): return
        yield event.plain_result(await handle_user_stats())