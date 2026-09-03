"""管理后台：掌握度查询（S3-M4 / 07 §4.3）

接口（挂 /api/admin 前缀，统一 require_perm 鉴权 + 审计落库）：
- GET /mastery/users/{user_id}  任意用户掌握度矩阵（按学科分组）  mastery:view_all
- GET /mastery/coverage         知识点标注覆盖率报表                content:view

逻辑均在 D4 学习引擎域（app.domains.engine.services.mastery_store），
本模块仅经 app.domains.engine.contracts 触达（import-linter 合规）。
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.admin import Admin

from . import router
from .common import _audit
from app.core.permissions import require_perm
from app.domains.engine import contracts as engine_contracts


@router.get("/mastery/users/{user_id}", summary="后台查询用户掌握度矩阵")
def admin_mastery_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("mastery:view_all")),
):
    """返回该用户的掌握度矩阵（按学科分组的逐知识点明细 + 整体汇总）。"""
    data = engine_contracts.get_user_mastery_matrix(db, user_id)
    _audit(db, admin, "mastery_view_user", f"user:{user_id}",
           f"查询用户掌握度矩阵，共 {data['overall']['total']} 个知识点")
    return data


@router.get("/mastery/coverage", summary="知识点标注覆盖率报表")
def admin_mastery_coverage(
    db: Session = Depends(get_db),
    admin: Admin = Depends(require_perm("content:view")),
):
    """知识点标注覆盖率（已标注/总数）、按学科拆分、掌握度落地进度。"""
    report = engine_contracts.get_coverage_report(db)
    _audit(db, admin, "mastery_coverage", "coverage",
           f"覆盖率报表：{report['annotated_kp']}/{report['total_kp']}"
           f"（coverage={report['coverage']}）")
    return report
