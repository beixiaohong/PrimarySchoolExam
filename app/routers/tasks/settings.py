"""每日任务配置（目标/启用/强制/可选/额度）相关端点"""
import json
from datetime import date, datetime

from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import router
from .common import *
from app.database import get_db
from app.services.parent_guard import ensure_parent_pwd
from app.models.daily_task import DailyTask


class SettingsRequest(BaseModel):
    """保存每日任务配置请求体：用户 ID 与配置字典（目标/启用/强制/可选/额度/学习开关）。"""
    user_id: str
    settings: dict = Field(default_factory=dict)


@router.get("/settings", summary="获取每日任务配置（目标+启用+强制/可选）")
def get_task_settings(user_id: str = Query(...), db: Session = Depends(get_db)):
    """获取每日任务配置（目标数/启用状态/追加强制任务/背诵额度/可选任务/学习开关）。

    参数（Query）：user_id。
    返回：{items[{code,subject,title,default,target,enabled,manual}], mandatory{学科:[追加codes]},
          quotas{每日新学单词/古诗文数}, optional[家长添加的可选code], study_flags{include_next/sync_mode/xsc_bridge}}。
    副作用：无（只读）。无需家长密码。
    """
    user = _load_settings(db, user_id)
    targets = user.get("targets", {})
    enabled_map = user.get("enabled", {})
    mandatory_map = user.get("mandatory", {})
    items = []
    all_tasks = list(MANDATORY_TASKS.values()) + OPTIONAL_POOL
    for code in CONFIGURABLE_CODES:
        item = next((t for t in all_tasks if t["code"] == code), None)
        if not item:
            continue
        subj = item.get("subject", "")
        if not subj:
            subj = next((s for s, t in MANDATORY_TASKS.items() if t["code"] == code), "")
        items.append({
            "code": code, "subject": subj, "title": item["title"],
            "default": item["target"], "target": targets.get(code, item["target"]),
            "enabled": enabled_map.get(code, True),
            "manual": item.get("manual", False),
        })
    current_mandatory = {}
    for subj in SUBJECTS:
        # 返回家长追加的强制任务 code 列表（默认任务后端保证存在，不存配置）
        current_mandatory[subj] = [c for c in mandatory_map.get(subj, [])
                                   if isinstance(c, str)]
    quotas = {k: int(user.get("quotas", {}).get(k, d)) for k, (_, _, d) in QUOTA_KEYS.items()}
    # 背诵类任务不在可配置列表，但作为强制任务时仍需返回 target 供前端回显数量
    for code in _UNCONFIGURABLE_CODES:
        item = next((t for t in all_tasks if t["code"] == code), None)
        if not item:
            continue
        subj = next((s for s, t in MANDATORY_TASKS.items() if t["code"] == code), "")
        items.append({
            "code": code, "subject": subj, "title": item["title"],
            "default": item["target"], "target": targets.get(code, item["target"]),
            "enabled": True, "manual": item.get("manual", False),
        })
    return {"items": items, "mandatory": current_mandatory, "quotas": quotas,
            "optional": user.get("optional", []),
            "study_flags": {k: bool(_load_study_flags(db, user_id).get(k, False))
                            for k in STUDY_FLAG_KEYS}}


@router.post("/settings", summary="保存每日任务配置（家长设置，需家长密码）")
def save_task_settings(req: SettingsRequest, request: Request, db: Session = Depends(get_db)):
    """保存每日任务配置（家长权限，需家长密码 X-Parent-Pwd）。

    参数（Body）：user_id、settings{targets/enabled/mandatory/quotas/optional/学习开关}。
    请求头：必须携带 X-Parent-Pwd（ensure_parent_pwd，否则 403）——防止孩子自行调低目标/禁用任务。
    返回：重新返回 get_task_settings 结构。
    副作用：upsert parent_task_settings；同步刷新今日未完成任务的目标/启用/追加项；
            目标数夹到 MIN_TARGET(1)-MAX_TARGET(50)，背诵类不可禁用。
    需要家长密码。
    """
    if not isinstance(req.settings, dict):
        raise HTTPException(400, "settings 必须为对象")
    # 防刷：任务配置是家长权限，孩子不得自行调低目标/禁用任务
    ensure_parent_pwd(db, req.user_id, request)

    # 学习开关单独提取（bool，可独立提交）
    flag_updates = {k: bool(req.settings[k]) for k in STUDY_FLAG_KEYS if k in req.settings}
    _payload = {k: v for k, v in req.settings.items() if k not in STUDY_FLAG_KEYS}

    existing = _load_settings(db, req.user_id)
    new_targets = dict(existing.get("targets", {}))
    new_enabled = dict(existing.get("enabled", {}))
    new_mandatory = dict(existing.get("mandatory", {}))
    new_quotas = dict(existing.get("quotas", {}))
    new_optional = list(existing.get("optional", []))

    # 家长添加的可选任务（code 列表，独立字段，可与其它字段分开提交）
    if "optional" in _payload:
        if not isinstance(_payload["optional"], list):
            raise HTTPException(400, "optional 必须为数组")
        seen, opt = set(), []
        for code in _payload["optional"]:
            if not isinstance(code, str) or code not in CONFIGURABLE_CODES:
                raise HTTPException(400, f"不支持的任务类型: {code}")
            if code not in seen:
                seen.add(code)
                opt.append(code)
        new_optional = opt

    if "targets" in _payload or "enabled" in _payload or "mandatory" in _payload \
            or "quotas" in _payload or "optional" in _payload:
        # 新格式
        if "targets" in _payload and isinstance(_payload["targets"], dict):
            for code, val in _payload["targets"].items():
                # 背诵类也允许保存目标数（仅展示用，完成判定仍为全量背诵+复习）
                if code not in CONFIGURABLE_CODES and code not in _UNCONFIGURABLE_CODES:
                    raise HTTPException(400, f"不支持的任务类型: {code}")
                try:
                    v = int(val)
                except (TypeError, ValueError):
                    raise HTTPException(400, f"{code} 的目标数量必须是整数")
                new_targets[code] = _bounded_target(code, v)
        if "enabled" in _payload and isinstance(_payload["enabled"], dict):
            for code, val in _payload["enabled"].items():
                if code in _UNCONFIGURABLE_CODES:
                    continue  # 强制背诵类任务不允许禁用，静默忽略
                if code not in CONFIGURABLE_CODES:
                    raise HTTPException(400, f"不支持的任务类型: {code}")
                new_enabled[code] = bool(val)
        if "mandatory" in _payload and isinstance(_payload["mandatory"], dict):
            for subj, val in _payload["mandatory"].items():
                if subj not in SUBJECTS:
                    raise HTTPException(400, f"不支持的学科: {subj}")
                # 兼容旧格式单 code 字符串；只存追加项，默认强制任务后端保证存在
                codes = [val] if isinstance(val, str) else (val if isinstance(val, list) else [])
                extra = []
                for code in codes:
                    if code == MANDATORY_TASKS[subj]["code"]:
                        continue
                    t = _task_def_by_code(code)
                    if not t or t.get("subject") != subj:
                        raise HTTPException(400, f"不支持的任务类型: {code}")
                    if code not in extra:
                        extra.append(code)
                new_mandatory[subj] = extra
        # 每日额度（家长配置：新学单词数 / 新背古诗文数）
        if "quotas" in _payload and isinstance(_payload["quotas"], dict):
            for key, val in _payload["quotas"].items():
                if key not in QUOTA_KEYS:
                    raise HTTPException(400, f"不支持的额度类型: {key}")
                lo, hi, _ = QUOTA_KEYS[key]
                try:
                    v = int(val)
                except (TypeError, ValueError):
                    raise HTTPException(400, f"{key} 必须是整数")
                if not lo <= v <= hi:
                    raise HTTPException(400, f"{key} 需在 {lo}-{hi} 之间")
                new_quotas[key] = v
    elif _payload:
        # 旧格式兼容：{code: int}
        for code, val in _payload.items():
            if code not in CONFIGURABLE_CODES and code not in _UNCONFIGURABLE_CODES:
                raise HTTPException(400, f"不支持的任务类型: {code}")
            try:
                v = int(val)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{code} 的目标数量必须是整数")
            new_targets[code] = _bounded_target(code, v)

    clean = {"targets": new_targets, "enabled": new_enabled,
             "mandatory": new_mandatory, "quotas": new_quotas,
             "optional": new_optional}
    # 学习开关持久化（顶层字段；未提交的保持原值）
    flags = _load_study_flags(db, req.user_id)
    flags.update(flag_updates)
    for k in STUDY_FLAG_KEYS:
        if k in flags:
            clean[k] = bool(flags[k])
    # 可移植 upsert（MySQL 兼容，不用 ON CONFLICT）
    _params = {"u": req.user_id, "j": json.dumps(clean), "t": datetime.now()}
    exists = db.execute(text("SELECT 1 FROM parent_task_settings WHERE user_id=:u"),
                        {"u": req.user_id}).fetchone()
    if exists:
        db.execute(text("UPDATE parent_task_settings SET settings_json=:j, updated_at=:t WHERE user_id=:u"), _params)
    else:
        db.execute(text("INSERT INTO parent_task_settings (user_id, settings_json, updated_at) "
                        "VALUES (:u, :j, :t)"), _params)
    today = date.today()
    rows = db.query(DailyTask).filter(
        DailyTask.user_id == req.user_id, DailyTask.task_date == today).all()
    for r in rows:
        if r.status != "done" and r.task_code in new_targets:
            r.target = new_targets[r.task_code]
    # 强制任务追加列表变更：删除今日未完成且已不在（默认+追加）列表中的强制行
    for r in rows:
        if getattr(r, "task_type", "") == "mandatory" and r.status != "done":
            valid = _get_mandatory_codes({"mandatory": new_mandatory}, r.subject)
            if r.task_code not in valid:
                db.delete(r)
    # 可选任务配置变更：删除今日未完成的可选行，下次 /daily 按新配置重新生成
    if new_optional != list(existing.get("optional", [])):
        for r in rows:
            if getattr(r, "task_type", "") == "optional" and r.status != "done":
                db.delete(r)
    db.commit()
    return get_task_settings(req.user_id, db)


__all__ = ["SettingsRequest", "get_task_settings", "save_task_settings"]
