"""M6 LLM Provider：OpenAI 兼容协议适配层（手册 12.1/12.6）。

配置（环境变量，密钥不入 Git / 不落盘 / 不进日志，AC30）：
    LLM_API_BASE    如 https://dashscope.aliyuncs.com/compatible-mode/v1
    LLM_API_KEY     甲方提供的密钥
    LLM_MODEL       如 qwen-plus / deepseek-chat / gpt-4o-mini
    LLM_TIMEOUT_S   调用超时（默认 45，手册 12.2）
    LLM_MAX_TOKENS  最大输出长度（默认 1024）

未配置时 llm_available() 返回 False，advice_service 直接走本地规则兜底。

日志约束（12.6）：只记录 provider、模型、耗时、状态、token 用量和
请求摘要哈希；不记录密钥与原始提示词。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time

import requests

log = logging.getLogger("v2.llm")

DEFAULT_TIMEOUT_S = 45.0
DEFAULT_MAX_TOKENS = 1024

_ADVICE_SECTIONS = ("risk_summary", "field_actions", "road_env", "enterprise", "education")
_OWNER_HINT = {
    "road_env": "道路与交通设施管理责任单位",
    "enterprise": "配送平台企业安全负责人",
    "education": "配送站点与平台企业培训负责人",
}


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def llm_config() -> dict:
    """当前 LLM 配置（密钥脱敏）。"""
    return {
        "api_base": _env("LLM_API_BASE"),
        "model": _env("LLM_MODEL"),
        "timeout_s": float(_env("LLM_TIMEOUT_S") or DEFAULT_TIMEOUT_S),
        "max_tokens": int(_env("LLM_MAX_TOKENS") or DEFAULT_MAX_TOKENS),
        "configured": llm_available(),
    }


def llm_available() -> bool:
    return bool(_env("LLM_API_BASE") and _env("LLM_API_KEY") and _env("LLM_MODEL"))


def _extract_json(text: str) -> dict | None:
    """解析模型返回；容忍 ```json 围栏与前后杂文。"""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(t[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def chat_json(system_prompt: str, user_prompt: str,
              timeout: float | None = None) -> dict | None:
    """调用 OpenAI 兼容 chat/completions，返回解析后的 JSON dict。

    任何失败（未配置/网络/超时/非 JSON）返回 None，由调用方兜底。
    """
    if not llm_available():
        return None
    cfg = llm_config()
    url = cfg["api_base"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": cfg["max_tokens"],
    }
    prompt_hash = hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()[:12]
    t0 = time.monotonic()
    status = "error"
    tokens = None
    try:
        resp = requests.post(
            url, json=payload, timeout=timeout or cfg["timeout_s"],
            headers={
                "Authorization": f"Bearer {_env('LLM_API_KEY')}",
                "Content-Type": "application/json",
            })
        status = f"http_{resp.status_code}"
        resp.raise_for_status()
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage") or {}
        tokens = usage.get("total_tokens")
        content = (choice.get("message") or {}).get("content") or ""
        obj = _extract_json(content)
        status = "ok" if obj is not None else "bad_json"
        return obj
    except Exception as exc:                     # noqa: BLE001
        log.warning("llm call failed: %s", type(exc).__name__)
        return None
    finally:
        dur = time.monotonic() - t0
        # 12.6：只记 provider/模型/耗时/状态/token/摘要哈希，不记密钥与原文
        log.info("llm provider=openai_compatible model=%s dur=%.1fs status=%s "
                 "tokens=%s prompt_hash=%s", cfg["model"], dur, status,
                 tokens, prompt_hash)


# ---------------------------------------------------------------------------
# 建议结构校验（12.5：JSON Schema 或等效校验 + 一次自动修复）
# ---------------------------------------------------------------------------

def _item_ok(item, keys: tuple[str, ...]) -> bool:
    return (isinstance(item, dict) and
            all(isinstance(item.get(k), str) and item.get(k).strip() for k in keys))


def validate_advice(obj: dict) -> list[str]:
    """校验 P-2.0 三部分结构（12.5），返回问题列表（空 = 合格）。

    field_actions 为五要素对象数组且必须非空；road_env/enterprise/education
    为 {trigger, measure, owner} 对象数组，允许为空。
    """
    problems: list[str] = []
    summary = obj.get("risk_summary")
    if not isinstance(summary, str) or not summary.strip():
        problems.append("risk_summary 必须为非空字符串")

    fa = obj.get("field_actions")
    if not isinstance(fa, list) or not fa:
        problems.append("field_actions 必须为非空数组")
    else:
        for i, item in enumerate(fa):
            if not _item_ok(item, ("when", "where", "deployment", "action", "completion")):
                problems.append(f"field_actions[{i}] 五要素字段缺失或非字符串")

    for key in _ADVICE_SECTIONS[2:]:
        val = obj.get(key)
        if not isinstance(val, list):
            problems.append(f"{key} 必须为数组")
            continue
        for i, item in enumerate(val):
            if not _item_ok(item, ("trigger", "measure", "owner")):
                problems.append(f"{key}[{i}] 缺少 trigger/measure/owner")

    if not isinstance(obj.get("basis_ids"), list) or \
            not all(isinstance(s, str) for s in obj.get("basis_ids", [])):
        problems.append("basis_ids 必须为字符串数组")
    return problems


def autofix_advice(obj: dict, fallback: dict) -> dict | None:
    """一次自动修复：结构不合格的部分用兜底模板补齐，合格部分保留。"""
    if not isinstance(obj, dict):
        return None
    fixed = dict(obj)

    if not (isinstance(fixed.get("risk_summary"), str) and fixed["risk_summary"].strip()):
        fixed["risk_summary"] = fallback.get("risk_summary")

    fa = fixed.get("field_actions")
    if isinstance(fa, list):
        # 丢弃缺五要素的项；全部不合格则整段走兜底
        keep = [it for it in fa
                if _item_ok(it, ("when", "where", "deployment", "action", "completion"))]
        fixed["field_actions"] = keep or fallback.get("field_actions")
    else:
        fixed["field_actions"] = fallback.get("field_actions")

    for key in _ADVICE_SECTIONS[2:]:
        val = fixed.get(key)
        if isinstance(val, str) and val.strip():
            # 模型把对象数组写成整段句子的情形：按句拆开包装为标准对象
            parts = [p.strip(" ;；") for p in
                     val.replace("\n", "。").replace("；", "。").split("。")
                     if p.strip(" ;；")]
            fixed[key] = [{"trigger": "数据达到命中规则条件时", "measure": p,
                           "owner": _OWNER_HINT[key]} for p in parts]
        elif isinstance(val, list):
            fixed[key] = [it for it in val if _item_ok(it, ("trigger", "measure", "owner"))]
        else:
            fixed[key] = fallback.get(key, [])

    bids = fixed.get("basis_ids")
    fixed["basis_ids"] = ([s for s in bids if isinstance(s, str)]
                          if isinstance(bids, list) else fallback.get("basis_ids", []))
    return fixed if not validate_advice(fixed) else None
