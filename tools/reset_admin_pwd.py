"""重置管理员后台登录密码（本地运维脚本，非接口）

仅用于「后台登录不上」时在本机/服务器手动重置默认管理员密码。
复用项目自身的 DB 配置与密码哈希，不暴露为任何 HTTP 接口。

用法（在项目根目录执行）：
  python tools/reset_admin_pwd.py                       # 重置 admin 为 Admin@123
  python tools/reset_admin_pwd.py --password "新密码"   # 指定新密码
  python tools/reset_admin_pwd.py --username ops --password "xxx"  # 指定账号

说明：
- 账号不存在时按默认凭证创建（role=super）；
- 账号存在时仅更新 password_hash，并清空当前 token（强制下次重新登录）；
- 新密码会过 _validate_pwd 强度校验（与后台「修改密码」同一规则）。
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models.admin import Admin  # noqa: E402
from app.domains.family.routers.parent import _hash_pwd, _validate_pwd  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="重置管理员后台密码")
    parser.add_argument("--username", default="admin", help="管理员用户名（默认 admin）")
    parser.add_argument("--password", default="Admin@123", help="新密码（默认 Admin@123）")
    args = parser.parse_args()

    username = args.username.strip()
    password = args.password

    try:
        _validate_pwd(password)
    except Exception as e:  # noqa: BLE001
        print(f"[错误] 密码不合规：{e}")
        sys.exit(2)

    db = SessionLocal()
    try:
        admin = db.query(Admin).filter(Admin.username == username).first()
        if admin is None:
            admin = Admin(username=username, role="super")
            db.add(admin)
            action = "创建"
        else:
            action = "更新"
        admin.password_hash = _hash_pwd(password)
        admin.token = None  # 强制重新登录
        admin.token_expires_at = None
        db.commit()
        print(f"[成功] 已{action}管理员 {username!r} 的密码（token 已清空，请重新登录）。")
    except Exception as e:  # noqa: BLE001
        db.rollback()
        print(f"[错误] 重置失败：{e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
