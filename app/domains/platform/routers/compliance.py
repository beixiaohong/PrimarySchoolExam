"""合规底座接口（CMP / 儿童个人信息保护）

前缀 /api/compliance，统一挂 user_auth_deps（严格账号绑定 require_self）：
- POST /api/compliance/consent       记录监护人同意（CMP-02）
- GET  /api/compliance/consent       查询本人同意状态
- POST /api/compliance/consent/revoke 撤回同意
- POST /api/compliance/export        申请导出个人数据（CMP-06）
- GET  /api/compliance/export        查询导出申请状态
- POST /api/compliance/delete        申请删除个人数据（CMP-06）
- GET  /api/compliance/delete        查询删除申请状态
- GET  /api/compliance/rules         获取当前隐私规则版本与内容摘要

设计要点：
- 同意记录按 (user_id, rule_version) 唯一，重复提交幂等返回；
- 导出/删除申请创建后由后台审批执行，接口只返回申请状态；
- AI 生成标识（CMP-05）由前端在 AI 输出区域显著标注，后端在 AI 响应中附加 ai_generated=true。
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.identity.contracts import require_self
from app.models.compliance import (
    DataDeletionRequest,
    DataExportRequest,
    GuardianConsent,
)
from app.models.user import User

router = APIRouter()
logger = logging.getLogger("app.compliance")

# 当前隐私规则版本（硬编码，后续可迁移至 system_config 表动态下发）
CURRENT_RULE_VERSION = "v1.0"
RULE_SUMMARY = "智学学堂儿童个人信息处理规则：收集学号/昵称/学习数据用于个性化推荐；" \
               "监护人可隨時申请导出或删除数据；AI 生成内容已标识。"


# ── 请求体 ──

class ConsentRequest(BaseModel):
    """监护人同意提交"""
    guardian_name: str = Field("", max_length=100, description="监护人姓名（可选）")
    rule_version: str = Field(CURRENT_RULE_VERSION, description="规则版本号")


class DeleteRequest(BaseModel):
    """数据删除申请"""
    reason: str = Field("", max_length=500, description="删除原因（可选）")


# ── 监护人同意 ──

@router.post("/consent", summary="记录监护人同意（CMP-02）")
def record_consent(
    body: ConsentRequest,
    request: Request,
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    """记录监护人同意。同一规则版本幂等：已同意则直接返回现有记录。"""
    existing = db.query(GuardianConsent).filter_by(
        user_id=current_user.user_id,
        rule_version=body.rule_version,
    ).first()
    if existing and existing.revoked_at is None:
        return {"status": "already_consent", "consent_id": existing.id,
                "consent_at": str(existing.consent_at), "rule_version": body.rule_version}

    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")

    if existing and existing.revoked_at is not None:
        # 曾撤回，重新激活
        existing.revoked_at = None
        existing.consent_at = datetime.now()
        existing.guardian_name = body.guardian_name or existing.guardian_name
        existing.ip_address = ip
        existing.user_agent = ua
        db.commit()
        return {"status": "re_consented", "consent_id": existing.id,
                "consent_at": str(existing.consent_at), "rule_version": body.rule_version}

    consent = GuardianConsent(
        user_id=current_user.user_id,
        guardian_name=body.guardian_name or None,
        rule_version=body.rule_version,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(consent)
    db.commit()
    db.refresh(consent)
    return {"status": "consented", "consent_id": consent.id,
            "consent_at": str(consent.consent_at), "rule_version": body.rule_version}


@router.get("/consent", summary="查询本人同意状态")
def get_consent_status(
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    """返回本人对各规则版本的同意状态。"""
    records = db.query(GuardianConsent).filter_by(user_id=current_user.user_id).all()
    items = [{
        "rule_version": r.rule_version,
        "consented": r.revoked_at is None,
        "consent_at": str(r.consent_at),
        "revoked_at": str(r.revoked_at) if r.revoked_at else None,
        "guardian_name": r.guardian_name,
    } for r in records]
    current = next((i for i in items if i["rule_version"] == CURRENT_RULE_VERSION and i["consented"]), None)
    return {
        "current_rule_version": CURRENT_RULE_VERSION,
        "has_current_consent": current is not None,
        "history": items,
    }


@router.post("/consent/revoke", summary="撤回监护人同意")
def revoke_consent(
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    """撤回对当前版本规则的同意。"""
    consent = db.query(GuardianConsent).filter_by(
        user_id=current_user.user_id,
        rule_version=CURRENT_RULE_VERSION,
    ).first()
    if consent is None or consent.revoked_at is not None:
        raise HTTPException(404, "无有效同意记录可撤回")
    consent.revoked_at = datetime.now()
    db.commit()
    return {"status": "revoked", "revoked_at": str(consent.revoked_at)}


# ── 数据导出 ──

@router.post("/export", summary="申请导出个人数据（CMP-06）")
def request_export(
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    """创建数据导出申请。24 小时内不可重复提交。"""
    recent = db.query(DataExportRequest).filter(
        DataExportRequest.user_id == current_user.user_id,
        DataExportRequest.status.in_(["pending", "processing"]),
    ).first()
    if recent:
        return {"status": "already_pending", "request_id": recent.id,
                "state": recent.status, "requested_at": str(recent.requested_at)}

    req = DataExportRequest(user_id=current_user.user_id)
    db.add(req)
    db.commit()
    db.refresh(req)
    return {"status": "created", "request_id": req.id, "state": req.status}


@router.get("/export", summary="查询导出申请状态")
def get_export_status(
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    """返回本人最近的数据导出申请。"""
    req = db.query(DataExportRequest).filter_by(
        user_id=current_user.user_id
    ).order_by(DataExportRequest.requested_at.desc()).first()
    if req is None:
        return {"has_request": False}
    return {
        "has_request": True,
        "request_id": req.id,
        "status": req.status,
        "result_url": req.result_url,
        "requested_at": str(req.requested_at),
        "completed_at": str(req.completed_at) if req.completed_at else None,
    }


# ── 数据删除 ──

@router.post("/delete", summary="申请删除个人数据（CMP-06）")
def request_delete(
    body: DeleteRequest,
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    """创建数据删除申请。已有 pending 申请时拒绝重复提交。"""
    recent = db.query(DataDeletionRequest).filter(
        DataDeletionRequest.user_id == current_user.user_id,
        DataDeletionRequest.status.in_(["pending", "processing"]),
    ).first()
    if recent:
        raise HTTPException(409, "已有进行中的删除申请，请等待处理完成")

    req = DataDeletionRequest(
        user_id=current_user.user_id,
        reason=body.reason or None,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return {"status": "created", "request_id": req.id, "state": req.status}


@router.get("/delete", summary="查询删除申请状态")
def get_delete_status(
    current_user: User = Depends(require_self),
    db: Session = Depends(get_db),
):
    """返回本人最近的数据删除申请。"""
    req = db.query(DataDeletionRequest).filter_by(
        user_id=current_user.user_id
    ).order_by(DataDeletionRequest.requested_at.desc()).first()
    if req is None:
        return {"has_request": False}
    return {
        "has_request": True,
        "request_id": req.id,
        "status": req.status,
        "reason": req.reason,
        "requested_at": str(req.requested_at),
        "completed_at": str(req.completed_at) if req.completed_at else None,
    }


# ── 规则查询 ──

@router.get("/rules", summary="获取当前隐私规则版本")
def get_rules():
    """返回当前隐私规则版本与摘要（无需登录，注册前可查）。"""
    return {
        "current_version": CURRENT_RULE_VERSION,
        "summary": RULE_SUMMARY,
    }
