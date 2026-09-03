"""家长鉴权守卫：敏感接口必须携带家长密码（防刷改造 P0）

背景：此前家长密码仅用于前端面板解锁，家长侧 API（任务配置、发券、
兑现心愿、手动确认任务等）可被孩子通过开发者工具直接调用。
本模块提供服务端校验：前端解锁后把密码暂存 sessionStorage，
调用敏感接口时通过请求头 X-Parent-Pwd 携带，服务端逐请求校验。
"""
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session


def _get_parent_password(db: Session, user_id: str):
    from app.models.parent import ParentPassword
    return db.query(ParentPassword).filter_by(user_id=user_id).first()


def ensure_parent_pwd(db: Session, user_id: str, request: Request) -> None:
    """校验请求头中的家长密码，失败抛 403。

    - 未设置家长密码：要求先设置（家长面板首次进入即引导）
    - 未携带密码头或密码错误：拒绝访问
    """
    from app.routers.parent import _verify_pwd

    p = _get_parent_password(db, user_id)
    if not p:
        raise HTTPException(403, "请先在家长管理中设置家长密码")
    pwd = request.headers.get("X-Parent-Pwd", "")
    if not pwd:
        raise HTTPException(403, "该操作需要家长身份，请先解锁家长管理")
    if not _verify_pwd(pwd, p.password_hash):
        raise HTTPException(403, "家长密码校验失败")
