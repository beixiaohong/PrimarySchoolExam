"""邮件发送服务（移植自 send_mail_code.py，配置改为 .env 环境变量）

用于注册/绑定/重置密码的验证码邮件。
SMTP_SSL + 30s 超时 + 最多 3 次重试（认证失败/收件人拒绝不重试）。
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from . import sysconfig

logger = logging.getLogger(__name__)

# SMTP 超时时间（秒）
SMTP_TIMEOUT = 30
# 最大重试次数
MAX_RETRY = 3


def mail_configured() -> bool:
    """邮件通道是否可用（发件地址与授权码都已配置，支持后台在线覆盖）"""
    return bool(sysconfig.get("MAIL_ADDRESS") and sysconfig.get("MAIL_PASSWORD"))


def send_email(
    to_email: str,
    code: str,
    subject: str = None,
    body_template: str = None,
) -> bool:
    """发送验证码邮件，成功返回 True"""
    if subject is None:
        subject = "验证码"
    if body_template is None:
        body_template = "您的验证码是：{code}，5 分钟内有效。如非本人操作请忽略。"

    body = body_template.format(code=code)
    sender_email = sysconfig.get("MAIL_ADDRESS")
    sender_password = sysconfig.get("MAIL_PASSWORD")

    if not sender_email or not sender_password:
        logger.error("邮件配置不完整：MAIL_ADDRESS 或 MAIL_PASSWORD 未设置")
        return False

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))

    server_host = sysconfig.get("MAIL_SERVER", "smtp.qiye.163.com")
    try:
        server_port = int(sysconfig.get("MAIL_PORT", "465"))
    except ValueError:
        server_port = 465

    for attempt in range(1, MAX_RETRY + 1):
        try:
            logger.info("尝试发送邮件 (%d/%d): %s", attempt, MAX_RETRY, to_email)
            server = smtplib.SMTP_SSL(server_host, server_port, timeout=SMTP_TIMEOUT)
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, message.as_string())
            server.quit()
            logger.info("邮件发送成功: %s", to_email)
            return True
        except smtplib.SMTPAuthenticationError as e:
            logger.error("SMTP 认证失败: %s", e)
            return False  # 认证失败不重试
        except smtplib.SMTPRecipientsRefused as e:
            logger.error("收件人拒绝: %s", e)
            return False  # 收件人错误不重试
        except smtplib.SMTPException as e:
            logger.error("SMTP 错误 (尝试 %d/%d): %s", attempt, MAX_RETRY, e)
            if attempt >= MAX_RETRY:
                return False
        except Exception as e:
            logger.error("邮件发送未知错误: %s: %s", type(e).__name__, e)
            if attempt >= MAX_RETRY:
                return False

    logger.error("邮件发送失败，已重试 %d 次: %s", MAX_RETRY, to_email)
    return False
