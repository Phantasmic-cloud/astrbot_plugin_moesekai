"""
src/common.py - 共享工具
"""

import json
from pathlib import Path


# ───────────────────────── 路径工具 ──────────────────────────────

def _plugin_dir() -> Path:
    return Path(__file__).parent.parent

def data_dir() -> Path:
    p = _plugin_dir() / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p

# ───────────────────────── 配置读取 ──────────────────────────────

_config: dict = {}

def set_config(cfg: dict):
    """由 main.py 在插件初始化时调用，注入配置"""
    global _config
    _config = cfg

def get_config() -> dict:
    return _config

# ───────────────────────── 群开关 ────────────────────────────────

def _switch_file() -> Path:
    return data_dir() / "group_switch.json"

def _load_switch() -> dict:
    f = _switch_file()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text("utf-8"))
    except Exception:
        return {}

def _save_switch(data: dict):
    _switch_file().write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def is_group_enabled(group_id: str) -> bool:
    """检查群是否已开启 moesekai 服务，默认关闭"""
    return _load_switch().get(str(group_id), False)

def set_group_enabled(group_id: str, enabled: bool):
    data = _load_switch()
    data[str(group_id)] = enabled
    _save_switch(data)

# ───────────────────────── 绑定数据读写 ──────────────────────────

def _bind_file() -> Path:
    return data_dir() / "bind_data.json"

def load_binds() -> dict:
    """{ "qq号": {"cn": "id或null", "tw": "id或null", "jp": "id或null", "default": "cn"} }"""
    f = _bind_file()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text("utf-8"))
    except Exception:
        return {}

def save_binds(data: dict):
    _bind_file().write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

def get_user_binds(binds: dict, qq: str) -> dict:
    if qq not in binds or not isinstance(binds[qq], dict):
        binds[qq] = {"cn": None, "tw": None, "jp": None, "default": None}
    return binds[qq]

def has_any_bind(user: dict) -> bool:
    return any(user.get(s) for s in ["cn", "tw", "jp"])

def mask_id(sekai_id: str) -> str:
    if len(sekai_id) <= 6:
        return sekai_id
    return "*" * (len(sekai_id) - 6) + sekai_id[-6:]

# ───────────────────────── 常量 ──────────────────────────────────

SERVERS     = ["cn", "tw", "jp"]
SERVER_NAME = {"cn": "国服", "tw": "台服", "jp": "日服"}