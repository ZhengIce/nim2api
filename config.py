import os
import tempfile

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib


def _env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEFAULTS = {
    "admin_password": os.getenv("NIM_GATEWAY_ADMIN_PASSWORD", "admin123"),
    "listen_port": _env_int("NIM_GATEWAY_LISTEN_PORT", 5010),
    "cooldown_seconds": _env_float("NIM_GATEWAY_COOLDOWN_SECONDS", 60),
    "upstream_base_url": os.getenv(
        "NIM_GATEWAY_UPSTREAM_BASE_URL",
        "https://integrate.api.nvidia.com/v1",
    ),
    "model_check_enabled": _env_bool("NIM_GATEWAY_MODEL_CHECK_ENABLED", False),
    "model_check_interval_minutes": _env_int(
        "NIM_GATEWAY_MODEL_CHECK_INTERVAL_MINUTES",
        60,
    ),
    "system_prompt_mode": os.getenv("NIM_GATEWAY_SYSTEM_PROMPT_MODE", "passthrough"),
    "system_prompt": os.getenv("NIM_GATEWAY_SYSTEM_PROMPT", ""),
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.getenv("NIM_GATEWAY_CONFIG", os.path.join(BASE_DIR, "config.toml"))
CONFIG_DIR = os.path.dirname(CONFIG_PATH)


def _load():
    if not os.path.exists(CONFIG_PATH):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(
                "# NVIDIA NIM 网关配置\n"
                f'admin_password = "{DEFAULTS["admin_password"]}"\n'
                f"listen_port = {DEFAULTS['listen_port']}\n"
                f"cooldown_seconds = {DEFAULTS['cooldown_seconds']}\n"
                f'upstream_base_url = "{DEFAULTS["upstream_base_url"]}"\n'
                f"model_check_enabled = {str(DEFAULTS['model_check_enabled']).lower()}\n"
                f"model_check_interval_minutes = {DEFAULTS['model_check_interval_minutes']}\n"
                f"system_prompt_mode = {_toml_string(str(DEFAULTS['system_prompt_mode']))}\n"
                f"system_prompt = {_toml_string(str(DEFAULTS['system_prompt']))}\n"
            )
        return dict(DEFAULTS)
    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    return merged


def _toml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _write(values):
    content = (
        "# NVIDIA NIM 网关配置\n"
        f"admin_password = {_toml_string(str(values['admin_password']))}\n"
        f"listen_port = {int(values['listen_port'])}\n"
        f"cooldown_seconds = {float(values['cooldown_seconds']):g}\n"
        f"upstream_base_url = {_toml_string(str(values['upstream_base_url']).rstrip('/'))}\n"
        f"model_check_enabled = {str(bool(values['model_check_enabled'])).lower()}\n"
        f"model_check_interval_minutes = {int(values['model_check_interval_minutes'])}\n"
        f"system_prompt_mode = {_toml_string(str(values['system_prompt_mode']))}\n"
        f"system_prompt = {_toml_string(str(values['system_prompt']))}\n"
    )
    os.makedirs(CONFIG_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix="config-", suffix=".toml", dir=CONFIG_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, CONFIG_PATH)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


_cfg = _load()

ADMIN_PASSWORD = str(_cfg["admin_password"])
LISTEN_PORT = int(_cfg["listen_port"])
COOLDOWN_SECONDS = float(_cfg["cooldown_seconds"])
UPSTREAM_BASE_URL = str(_cfg["upstream_base_url"]).rstrip("/")
MODEL_CHECK_ENABLED = bool(_cfg["model_check_enabled"])
MODEL_CHECK_INTERVAL_MINUTES = int(_cfg["model_check_interval_minutes"])
SYSTEM_PROMPT_MODE = str(_cfg["system_prompt_mode"])
SYSTEM_PROMPT = str(_cfg["system_prompt"])

DATA_DIR = os.getenv("NIM_GATEWAY_DATA_DIR", os.path.join(BASE_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "gateway.db")


def update_settings(values):
    global ADMIN_PASSWORD, LISTEN_PORT, COOLDOWN_SECONDS, UPSTREAM_BASE_URL
    global MODEL_CHECK_ENABLED, MODEL_CHECK_INTERVAL_MINUTES
    global SYSTEM_PROMPT_MODE, SYSTEM_PROMPT

    merged = {
        "admin_password": ADMIN_PASSWORD,
        "listen_port": LISTEN_PORT,
        "cooldown_seconds": COOLDOWN_SECONDS,
        "upstream_base_url": UPSTREAM_BASE_URL,
        "model_check_enabled": MODEL_CHECK_ENABLED,
        "model_check_interval_minutes": MODEL_CHECK_INTERVAL_MINUTES,
        "system_prompt_mode": SYSTEM_PROMPT_MODE,
        "system_prompt": SYSTEM_PROMPT,
    }
    merged.update(values)
    _write(merged)

    ADMIN_PASSWORD = str(merged["admin_password"])
    LISTEN_PORT = int(merged["listen_port"])
    COOLDOWN_SECONDS = float(merged["cooldown_seconds"])
    UPSTREAM_BASE_URL = str(merged["upstream_base_url"]).rstrip("/")
    MODEL_CHECK_ENABLED = bool(merged["model_check_enabled"])
    MODEL_CHECK_INTERVAL_MINUTES = int(merged["model_check_interval_minutes"])
    SYSTEM_PROMPT_MODE = str(merged["system_prompt_mode"])
    SYSTEM_PROMPT = str(merged["system_prompt"])
