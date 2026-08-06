"""AI 服务层：多提供商路由（免费链 → VIP 付费链），零第三方依赖（urllib）

提供商（配置优先级：系统环境变量 > 项目根目录 .env 文件）：
- zhipu（免费）：智谱 GLM，ZHIPU_API_KEY；AI_MODEL / AI_BASE_URL 可覆盖
  - 付费优先：主模型 glm-4.7 标准版（关闭思考防超时），余额耗尽/无有效输出时自动回退免费版 glm-4.7-flash
  - 程序内部全局节流（AI_THROTTLE_SEC）控制请求频率，避免超时/限流
- relay（备用兜底）：第三方 OpenAI 兼容中转站，RELAY_API_KEY / RELAY_BASE_URL / RELAY_MODEL 配置；
  智谱失败/无有效输出后自动尝试，仅兜底不抢主链路；未配置 Key 时自动跳过
- deepseek（付费）：DeepSeek，DEEPSEEK_API_KEY，接口 https://api.deepseek.com，模型 deepseek-v4-flash

路由规则：
- 所有用户：免费链 [zhipu, relay]（glm-4.7 付费优先，余额耗尽自动切免费版 glm-4.7-flash，再失败由中转站兜底）
- VIP 用户（名单存数据库 vip_users 表，按 user_id 精确匹配）：免费链全部失败后再尝试付费链 [deepseek]
- 付费链按 user_id 独立限频（PAID_DAILY_LIMIT 次/天），防止单个用户刷爆付费 API
- 未配置 Key 的提供商直接跳过；全链失败返回 None，由路由层降级为本地模板

余额耗尽降级：调用付费主模型收到智谱欠费/额度错误码（1113/1308/1310/1311/1316-1321）后，
标记 PAID_EXHAUSTED_TTL 秒内直接使用免费备用模型，避免每次请求都浪费一次必然失败的调用。

降级约定：所有对外函数在不可用时返回 None / {"degraded": True, ...}，
由路由层转为本地模板，前端无感。
"""
import json
import logging
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ai")

TIMEOUT_SEC = 10  # 默认超时；提供商可覆盖（cfg["timeout"]）

# ── VIP 名单（数据库 vip_users 表，按 user_id 隔离付费链） ──
# 增删 VIP：直接操作 primary_school.db 的 vip_users 表（INSERT/DELETE），
# 服务层最多 60 秒后自动生效（内存缓存 TTL），无需重启。
VIP_CACHE_TTL = 60          # VIP 名单内存缓存秒数
PAID_DAILY_LIMIT = 100      # 付费链：每个 VIP user_id 每天最多调用次数（防刷）


def _vip_db_path() -> Path:
    """VIP 名单数据库路径（项目根 primary_school.db）"""
    return Path(__file__).resolve().parent.parent.parent / "primary_school.db"


def _load_vip_users() -> set:
    """从 vip_users 表读取名单；失败返回空集（不阻断启动/调用）"""
    try:
        conn = sqlite3.connect(str(_vip_db_path()))
        try:
            return {r[0] for r in conn.execute("SELECT user_id FROM vip_users")}
        finally:
            conn.close()
    except Exception as e:
        logger.warning("读取 VIP 名单失败: %s", e)
        return set()


_vip_cache: set = set()
_vip_cache_ts: float = 0.0


def _is_vip(user_id: str) -> bool:
    """VIP 判定：内存缓存（VIP_CACHE_TTL 秒）→ 数据库 vip_users 表"""
    global _vip_cache, _vip_cache_ts
    if time.time() - _vip_cache_ts > VIP_CACHE_TTL:
        _vip_cache = _load_vip_users()
        _vip_cache_ts = time.time()
    return user_id in _vip_cache

# ── 提供商注册表 ──
# tier: free=免费链（所有用户），paid=付费链（仅 VIP）
PROVIDERS: dict = {
    "zhipu": {
        "label": "智谱 GLM",
        "tier": "free",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        # 付费优先：主模型用标准版；余额耗尽/无有效输出自动回退免费版 flash
        "model": "glm-4.7",
        "fallback_model": "glm-4.7-flash",
        "env_model": "AI_MODEL",
        "env_base": "AI_BASE_URL",
        # 关闭思考后实测 1.8-2.2s 返回；12s 上限：服务端过载时快速失败回退免费版，避免用户久等
        "timeout": 12,
        # 关闭思考：glm-4.7 思考阶段实测 6-60s 经常超时，关闭后 2.2s 稳定返回
        "extra_params": {"thinking": {"type": "disabled"}},
    },
    "deepseek": {
        "label": "DeepSeek",
        "tier": "paid",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
    },
    # 第三方 OpenAI 兼容中转站（备用兜底）：RELAY_* 环境变量配置，未配置自动跳过
    "relay": {
        "label": "中转站",
        "tier": "free",
        "base_url": "",  # 默认空 → 必须配置 RELAY_BASE_URL 才有意义
        "model": "gpt-4o-mini",  # 默认模型；RELAY_MODEL 可覆盖
        "env_key": "RELAY_API_KEY",
        "env_base": "RELAY_BASE_URL",
        "env_model": "RELAY_MODEL",
        "timeout": 20,  # 中转站为套壳转发，链路长，放宽超时
    },
}

FREE_CHAIN = ["zhipu", "relay"]
PAID_CHAIN = ["deepseek"]

# ── 付费余额耗尽标记（账户级，全局） ──
# 智谱错误码（docs.bigmodel.cn/cn/faq/api-code）：1113 账户欠费、1308 使用上限、
# 1310 免费用户额度用尽、1311 订阅不授予访问权限、1316-1321 上限/余额组合
FUNDS_ERROR_CODES = {"1113", "1308", "1310", "1311", "1316", "1317", "1318", "1319", "1320", "1321"}
PAID_EXHAUSTED_TTL = 6 * 3600  # 标记冷却 6 小时：期间不再尝试付费主模型
PAID_PRIMARY_MODELS = {"glm-4.7"}  # 免费提供商内的付费优先模型（收到额度错误码即标记耗尽）

_paid_exhausted_until: float = 0.0


def _mark_paid_exhausted() -> None:
    """记录付费余额耗尽时刻（账户级：API Key 共享，一个用户触发全体生效）"""
    global _paid_exhausted_until
    _paid_exhausted_until = time.time() + PAID_EXHAUSTED_TTL
    logger.warning("AI 检测到付费余额耗尽，%d 秒内直接使用免费备用模型", PAID_EXHAUSTED_TTL)


def _paid_exhausted() -> bool:
    return time.time() < _paid_exhausted_until


# ── 全局节流：并发请求排队，避免打满速率限制/超时 ──
_throttle_lock = threading.Lock()
_last_ai_call_ts: float = 0.0
AI_THROTTLE_SEC = 1.0  # 相邻两次 AI 请求最小间隔（秒）；单元测试中可置 0


def _throttle() -> None:
    """全局互斥节流：并发请求串行化，每次请求至少间隔 AI_THROTTLE_SEC"""
    global _last_ai_call_ts
    with _throttle_lock:
        wait = _last_ai_call_ts + AI_THROTTLE_SEC - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_ai_call_ts = time.time()


def _chain_for(user_id: str) -> list:
    """返回该用户的调用链：免费链 +（VIP 时）付费链（名单存数据库）"""
    chain = list(FREE_CHAIN)
    if _is_vip(user_id):
        chain.extend(PAID_CHAIN)
    return chain


# ── .env 加载（仅首次调用时执行一次） ──
_env_loaded = False


def _load_env_file() -> None:
    """读取项目根目录 .env（KEY=VALUE 简单格式），不覆盖已有环境变量"""
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    try:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
            logger.info("已从 %s 加载环境配置", env_path)
    except OSError as e:  # 读取失败不阻断启动
        logger.warning("读取 .env 失败: %s", e)


def _config_provider(name: str) -> dict:
    """返回提供商调用配置；未配置 Key 时 api_key 为空串"""
    _load_env_file()
    p = PROVIDERS[name]
    cfg = {
        "api_key": "",
        "base_url": p["base_url"],
        "model": p["model"],
    }
    if name == "zhipu":
        cfg["api_key"] = os.environ.get("ZHIPU_API_KEY", "").strip()
        cfg["model"] = os.environ.get("AI_MODEL", p["model"])
        cfg["base_url"] = os.environ.get("AI_BASE_URL", p["base_url"]).rstrip("/")
        cfg["fallback_model"] = p.get("fallback_model", "")
    elif name == "deepseek":
        cfg["api_key"] = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    elif name == "relay":
        # 中转站：RELAY_API_KEY / RELAY_BASE_URL / RELAY_MODEL 均可覆盖；未配置 Key 自动跳过
        cfg["api_key"] = os.environ.get(p.get("env_key", "RELAY_API_KEY"), "").strip()
        cfg["model"] = os.environ.get(p.get("env_model", "RELAY_MODEL"), p["model"])
        cfg["base_url"] = os.environ.get(p.get("env_base", "RELAY_BASE_URL"), p["base_url"]).rstrip("/")
    if p.get("timeout"):
        cfg["timeout"] = p["timeout"]  # 推理模型需更长超时
    if p.get("extra_params"):
        cfg["extra_params"] = p["extra_params"]  # 如关闭思考，避免超时
    return cfg


def ai_enabled() -> bool:
    """任一免费提供商配置了 Key 即视为 AI 可用"""
    _load_env_file()
    return any(_config_provider(n)["api_key"] for n in FREE_CHAIN)


# ── 简单内存限频器 ──
_rate_buckets: dict = {}


def rate_limit(key: str, max_calls: int, window_sec: int) -> bool:
    """限频：窗口内超过 max_calls 返回 False（拒绝）"""
    now = time.time()
    bucket = _rate_buckets.setdefault(key, [])
    bucket[:] = [t for t in bucket if now - t < window_sec]
    if len(bucket) >= max_calls:
        return False
    bucket.append(now)
    return True


def _http_call(cfg: dict, system: str, user: str, max_tokens: int,
               _attempt: int = 0) -> dict:
    """单次 OpenAI 兼容 POST；429 时短暂等待重试一次；开头全局节流防超时/限流"""
    _throttle()
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": False,
    }
    # 提供商附加参数（如 glm-4.7 关闭思考：{"thinking": {"type": "disabled"}}）
    payload.update(cfg.get("extra_params", {}) or {})
    req = urllib.request.Request(
        cfg["base_url"] + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {cfg['api_key']}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg.get("timeout", TIMEOUT_SEC)) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 免费档易被限流（429）→ 短暂等待重试一次
        if e.code == 429 and _attempt == 0:
            time.sleep(1.5)
            return _http_call(cfg, system, user, max_tokens, _attempt=1)
        raise


def _call_provider(name: str, cfg: dict, system: str, user: str,
                   max_tokens: int) -> Optional[dict]:
    """调用单个提供商：付费主模型无有效输出时自动回退免费备用模型"""
    fb = cfg.get("fallback_model")
    # 付费余额已耗尽：跳过必然失败的付费主模型，直接用免费备用
    if (cfg["model"] in PAID_PRIMARY_MODELS and fb and fb != cfg["model"]
            and _paid_exhausted()):
        logger.info("AI[%s] 付费模型 %s 余额已耗尽，直接使用免费备用 %s",
                    name, cfg["model"], fb)
        fb_cfg = dict(cfg)
        fb_cfg["model"] = fb
        return _call_model(fb_cfg, system, user, max_tokens)
    result = _call_model(cfg, system, user, max_tokens)
    if result and result["text"].strip():
        return result
    if fb and fb != cfg["model"]:
        fb_cfg = dict(cfg)
        fb_cfg["model"] = fb
        logger.info("AI[%s] 主模型 %s 无有效输出，自动回退 %s",
                    name, cfg["model"], fb)
        return _call_model(fb_cfg, system, user, max_tokens)
    return result


def _call_model(cfg: dict, system: str, user: str,
                max_tokens: int) -> Optional[dict]:
    """调用单个模型，返回 {"text", ...}；失败/异常返回 None"""
    try:
        data = _http_call(cfg, system, user, max_tokens)
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content", "").strip()
        # 推理模型（如 glm-4.7-flash）会把 token 预算耗在思考上，
        # 导致 content 为空且 finish_reason=length → 扩容重试一次
        if not content and choice.get("finish_reason") == "length":
            data = _http_call(cfg, system, user, min(max(max_tokens * 10, 900), 2500))
            choice = (data.get("choices") or [{}])[0]
            content = (choice.get("message") or {}).get("content", "").strip()
        usage = data.get("usage", {})
        return {
            "text": content,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "model": cfg["model"],
        }
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        logger.warning("AI[%s] HTTP %s: %s", cfg["model"], e.code, body)
        # 付费主模型收到欠费/额度错误码 → 标记余额耗尽，后续直接走免费备用
        if cfg["model"] in PAID_PRIMARY_MODELS:
            try:
                code = str((json.loads(body) or {}).get("error", {}).get("code", ""))
                if code in FUNDS_ERROR_CODES:
                    _mark_paid_exhausted()
            except Exception:
                pass
        return None
    except Exception as e:  # 超时/连接失败等
        logger.warning("AI[%s] 调用失败: %s", cfg["model"], e)
        return None


def chat_for(user_id: str, system: str, user: str, max_tokens: int = 800) -> Optional[dict]:
    """按用户调用链取 AI 结果。

    - 免费链（zhipu, relay）对所有用户开放：glm-4.7 付费优先，余额耗尽/无有效输出自动回退免费版 glm-4.7-flash，再失败由中转站兜底
    - VIP 用户（数据库 vip_users 表，按 user_id 判定）在免费链全部失败后追加付费链（deepseek）
    - 付费链按 user_id 独立日配额（PAID_DAILY_LIMIT），配额用尽直接返回 None（防刷）
    - 未配置 Key 的提供商跳过；全链失败返回 None（路由层降级模板）

    成功返回 {"text", "prompt_tokens", "completion_tokens", "model", "provider"}。
    """
    chain = _chain_for(user_id)
    tried: list = []
    for name in chain:
        if name in PAID_CHAIN and not rate_limit(f"paid:{user_id}", PAID_DAILY_LIMIT, 86400):
            logger.warning("AI 付费链日配额用尽（user=%s, limit=%d），降级模板", user_id, PAID_DAILY_LIMIT)
            return None
        cfg = _config_provider(name)
        if not cfg["api_key"]:
            continue
        tried.append(name)
        result = _call_provider(name, cfg, system, user, max_tokens)
        if result and result["text"].strip():
            result["provider"] = name
            return result
    if not tried:
        logger.info("AI 未配置任何可用 Key（user=%s 链=%s），返回 None", user_id, chain)
    return None


def chat(system: str, user: str, max_tokens: int = 800) -> Optional[dict]:
    """旧签名兼容：走免费链（不区分用户）"""
    return chat_for("", system, user, max_tokens)
