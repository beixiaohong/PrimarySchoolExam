"""AI 服务层：多提供商路由（免费链 → VIP 付费链），零第三方依赖（urllib）

提供商（配置优先级：系统环境变量 > 项目根目录 .env 文件）：
- zhipu（免费）：智谱 GLM，ZHIPU_API_KEY；AI_MODEL / AI_BASE_URL 可覆盖
  - 主模型 glm-4.7-flash，无有效输出（限流/报错/空响应）时自动回退 glm-4.7 标准版
- deepseek（付费）：DeepSeek，DEEPSEEK_API_KEY，接口 https://api.deepseek.com，模型 deepseek-chat

路由规则：
- 所有用户：免费链 [zhipu]（flash 失败自动切 glm-4.7 标准版）
- VIP 用户（VIP_USERS 硬编码名单）：免费链全部失败后再尝试付费链 [deepseek]
- 未配置 Key 的提供商直接跳过；全链失败返回 None，由路由层降级为本地模板

降级约定：所有对外函数在不可用时返回 None / {"degraded": True, ...}，
由路由层转为本地模板，前端无感。
"""
import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ai")

TIMEOUT_SEC = 10  # 默认超时；提供商可覆盖（cfg["timeout"]）

# ── VIP 名单：暂时在此硬编码（暂无管理后台，防止付费 API 被刷） ──
# 例：VIP_USERS = {"朵朵", "小帅"} —— 付费链（deepseek）只对名单内用户开放
# 按登录用户名精确匹配（user_id in VIP_USERS）
VIP_USERS: set = {"诗文", "橙子"}

# ── 提供商注册表 ──
# tier: free=免费链（所有用户），paid=付费链（仅 VIP）
PROVIDERS: dict = {
    "zhipu": {
        "label": "智谱 GLM",
        "tier": "free",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4.7-flash",
        "fallback_model": "glm-4.7",  # flash 无有效输出时自动回退标准版
        "env_model": "AI_MODEL",
        "env_base": "AI_BASE_URL",
        "timeout": 20,  # 推理模型响应慢（实测 ≥10s），默认 10s 经常超时
    },
    "deepseek": {
        "label": "DeepSeek",
        "tier": "paid",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
}

FREE_CHAIN = ["zhipu"]
PAID_CHAIN = ["deepseek"]


def _chain_for(user_id: str) -> list:
    """返回该用户的调用链：免费链 +（VIP 时）付费链"""
    chain = list(FREE_CHAIN)
    if user_id in VIP_USERS:
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
    if p.get("timeout"):
        cfg["timeout"] = p["timeout"]  # 推理模型需更长超时
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
    """单次 OpenAI 兼容 POST；429 时短暂等待重试一次"""
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
    """调用单个提供商：主模型无有效输出时自动回退备用模型（如 glm-4.7 标准版）"""
    result = _call_model(cfg, system, user, max_tokens)
    if result and result["text"].strip():
        return result
    fb = cfg.get("fallback_model")
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
        return None
    except Exception as e:  # 超时/连接失败等
        logger.warning("AI[%s] 调用失败: %s", cfg["model"], e)
        return None


def chat_for(user_id: str, system: str, user: str, max_tokens: int = 800) -> Optional[dict]:
    """按用户调用链取 AI 结果。

    - 免费链（zhipu）对所有用户开放：glm-4.7-flash 无有效输出自动回退 glm-4.7 标准版
    - VIP 用户（VIP_USERS）在免费链全部失败后追加付费链（deepseek）
    - 未配置 Key 的提供商跳过；全链失败返回 None（路由层降级模板）

    成功返回 {"text", "prompt_tokens", "completion_tokens", "model", "provider"}。
    """
    chain = _chain_for(user_id)
    tried: list = []
    for name in chain:
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
