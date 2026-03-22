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

    event_id = event["id"]
    url      = url_tpl.replace("{event_id}", str(event_id)).replace("{region}", region)

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
    items    = (cache.get("data") or {}).get("items", [])
    rank_map = {item["rank"]: item for item in items if "rank" in item}

    lines = [
        f"当前活动({region.upper()})：第{event_id}期",
        event_name,
        "----------------",
    ]
    for rank in ranks:
        item = rank_map.get(rank)
        if not item:
            continue
        prediction = item.get("prediction")
        if prediction is None or float(prediction) == 0:
            continue
        lines.append(f"{rank}位: {_fmt_score(prediction)}")

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

    cfg = get_config()
    if cfg.get("forecast_image_enabled", False):
        img_bytes = await build_forecast_image(target, cache, current_event)
        if img_bytes:
            return ("image", img_bytes)
        # 渲染失败降级到文字
    return build_forecast_msg(target, cache)

# ───────────────────────── 图片渲染 ──────────────────────────────

# 渐变方案：(底色渐变CSS, logo文件名)
_THEMES = [
    ("135deg, #2a4a7f 0%, #6ab0e0 100%", "moe_blue.png"),
    ("135deg, #7b2d8b 0%, #f0a0d0 100%", "moe_pink.png"),
    ("135deg, #c0507a 0%, #d890a0 100%", "moe_lightpink.png"),
    ("135deg, #8b7a00 0%, #c8b840 100%", "moe_yellow.png"),
]

def _ms_to_beijing(ms: int) -> str:
    """毫秒时间戳转北京时间字符串"""
    from datetime import timedelta
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc) + timedelta(hours=8)
    return dt.strftime("%Y-%m-%d %H:%M")

def _build_forecast_html(region: str, cache: dict, current_event: dict) -> str:
    import random, base64
    from .common import data_dir

    cfg        = get_config()
    ranks      = cfg.get("forecast_ranks", [50, 100, 200, 300, 500, 1000, 2000, 3000, 5000, 10000, 50000])
    event_id   = cache.get("event_id", "?")
    event_name = cache.get("event_name", "")
    fetch_time = _fmt_time_ago(cache.get("fetch_time", ""))
    pred_time  = _fmt_time_ago(cache.get("predict_time", ""))

    # 活动时间
    start_ms    = current_event.get("startAt", 0)
    end_ms      = current_event.get("aggregateAt", current_event.get("closedAt", 0))
    start_str   = _ms_to_beijing(start_ms) if start_ms else "-"
    end_str     = _ms_to_beijing(end_ms) if end_ms else "-"

    # 剩余时间
    now_ms      = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
    remain_ms   = end_ms - now_ms if end_ms > now_ms else 0
    remain_days = remain_ms // (1000 * 60 * 60 * 24)
    remain_hrs  = (remain_ms % (1000 * 60 * 60 * 24)) // (1000 * 60 * 60)
    remain_mins = (remain_ms % (1000 * 60 * 60)) // (1000 * 60)
    if remain_ms > 0:
        remain_str = f"距离活动结束还有{remain_days}天{remain_hrs}小时{remain_mins}分钟"
    else:
        remain_str = "活动已结束"

    # 随机主题
    theme = random.choice(_THEMES)
    gradient, logo_file = theme

    # logo base64
    logo_path = data_dir() / "moelogo" / logo_file
    logo_b64  = ""
    if logo_path.exists():
        logo_b64 = base64.b64encode(logo_path.read_bytes()).decode()
    logo_src = f"data:image/png;base64,{logo_b64}" if logo_b64 else ""

    # 字体base64
    font_path = data_dir() / "fonts" / "SourceHanSansCN-Heavy.otf"
    font_b64  = ""
    if font_path.exists():
        font_b64 = base64.b64encode(font_path.read_bytes()).decode()
    font_face = f"""
    @font-face {{
        font-family: 'SourceHan';
        src: url('data:font/otf;base64,{font_b64}') format('opentype');
    }}
    """ if font_b64 else ""

    # 数据行
    items    = (cache.get("data") or {}).get("items", [])
    rank_map = {item["rank"]: item for item in items if "rank" in item}
    rows_html = ""
    row_count = 0
    for rank in ranks:
        item = rank_map.get(rank)
        if not item:
            continue
        score      = item.get("score")
        prediction = item.get("prediction")
        if prediction is None or float(prediction) == 0:
            continue
        score_str = _fmt_score(score) if score is not None else "-"
        pred_str  = _fmt_score(prediction)
        bg = "rgba(255,255,255,0.08)" if row_count % 2 == 0 else "transparent"
        rows_html += f"""
        <tr style="background:{bg}">
            <td>{rank:,}</td>
            <td>{score_str}</td>
            <td>{pred_str}</td>
        </tr>"""
        row_count += 1

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
{font_face}
* {{ margin:0; padding:0; box-sizing:border-box; font-family:'SourceHan', sans-serif; }}
body {{
    width: 660px;
    background: linear-gradient({gradient});
    padding: 20px;
}}
.top-card {{
    background: rgba(255,255,255,0.18);
    backdrop-filter: blur(8px);
    border-radius: 14px;
    padding: 16px 18px;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}}
.top-left {{ flex: 1; }}
.top-left .tag {{
    display: inline-block;
    background: rgba(255,255,255,0.35);
    color: #fff;
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 6px;
    margin-bottom: 6px;
}}
.top-left .title {{
    color: #fff;
    font-size: 22px;
    font-weight: bold;
    margin-bottom: 4px;
}}
.top-left .time {{
    color: rgba(255,255,255,0.85);
    font-size: 15px;
    margin-bottom: 3px;
}}
.top-left .remain {{
    color: #fff;
    font-size: 17px;
    font-weight: bold;
}}
.logo {{
    width: 180px;
    height: auto;
    object-fit: contain;
    margin-left: 16px;
    opacity: 0.9;
    align-self: center;
}}
.table-card {{
    background: rgba(255,255,255,0.18);
    backdrop-filter: blur(8px);
    border-radius: 14px;
    overflow: hidden;
    margin-bottom: 10px;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    color: #fff;
    font-size: 17px;
}}
thead tr {{
    background: rgba(255,255,255,0.25);
}}
thead th {{
    padding: 10px 14px;
    text-align: center;
    font-size: 17px;
    font-weight: bold;
}}
tbody td {{
    padding: 9px 14px;
    text-align: center;
    font-size: 14px;
}}
.footer {{
    text-align: right;
    color: rgba(255,255,255,0.7);
    font-size: 12px;
    margin-top: 4px;
}}
</style>
</head>
<body>
<div class="top-card">
    <div class="top-left">
        <div class="tag">活动</div>
        <div class="title">【{region.upper()}-{event_id}】{event_name}</div>
        <div class="time">{start_str} ~ {end_str}</div>
        <div class="remain">{remain_str}</div>
    </div>
    {"<img class='logo' src='" + logo_src + "'>" if logo_src else ""}
</div>
<div class="table-card">
    <table>
        <thead>
            <tr>
                <th>排名</th>
                <th>当前榜线</th>
                <th>Moesekai预测</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
            <tr style="background:rgba(255,255,255,0.08)">
                <td style="font-size:13px">预测时间</td>
                <td>-</td>
                <td style="font-size:13px">{pred_time}</td>
            </tr>
            <tr>
                <td style="font-size:13px">获取时间</td>
                <td style="font-size:13px">{fetch_time}</td>
                <td style="font-size:13px">{fetch_time}</td>
            </tr>
        </tbody>
    </table>
</div>
<div class="footer">数据来源: pjsk.moe(by 東雪) &nbsp;&nbsp; From Phantasmic(郁郁葱葱)</div>
</body>
</html>"""
    return html


async def build_forecast_image(region: str, cache: dict, current_event: dict) -> bytes | None:
    """用Playwright渲染预测线图片，返回JPEG bytes"""
    try:
        from playwright.async_api import async_playwright
        import tempfile, os

        html = _build_forecast_html(region, cache, current_event)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html",
                                         delete=False, encoding="utf-8") as f:
            f.write(html)
            tmp_path = f.name

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page    = await browser.new_page(viewport={"width": 660, "height": 900}, device_scale_factor=2)
                await page.goto(f"file://{tmp_path}", wait_until="networkidle")
                # 自适应高度
                height = await page.evaluate("document.body.scrollHeight")
                await page.set_viewport_size({"width": 660, "height": height})
                img_bytes = await page.screenshot(
                    full_page=True,
                    type="jpeg",
                    quality=90,
                )
                await browser.close()
            return img_bytes
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        logger.warning(f"[sk_forecast] 渲染图片失败: {e}")
        return None
