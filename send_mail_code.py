"""
邮件验证码发送模块
=================

功能：
- 生成随机验证码
- 发送验证码邮件
- 支持自定义邮件内容

作者：开发团队
版本：1.0.0
"""
import random
import string
import smtplib
import logging
from typing import Optional
from backend.base_config.localconfig import emailconfig
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 配置日志
logger = logging.getLogger(__name__)

# SMTP超时时间（秒）
SMTP_TIMEOUT = 30
# 最大重试次数
MAX_RETRY = 3

def generate_verification_code(length: int = 6) -> str:
    """
    生成指定长度的随机验证码
    
    用途：
    生成纯数字验证码，用于用户注册、找回密码等场景的身份验证。
    
    Args:
        length: 验证码长度，默认为6位
        
    Returns:
        str: 生成的随机验证码字符串（纯数字）
        
    Example:
        >>> generate_verification_code()
        '123456'
        >>> generate_verification_code(4)
        '7890'
        
    Note:
        - 使用数字字符集（0-9）
        - 每次调用生成新的随机码
        - 适合短信和邮件验证码场景
    """
    if length <= 0:
        raise ValueError("验证码长度必须大于0")
    
    characters = string.digits  # 选择数字作为验证码字符集
    return ''.join(random.choice(characters) for _ in range(length))

def send_email(
    to_email: str, 
    code: str,
    subject: Optional[str] = None,
    body_template: Optional[str] = None
) -> bool:
    """
    发送验证码邮件
    
    用途：
    向用户邮箱发送包含验证码的邮件，支持自定义主题和正文模板。
    
    Args:
        to_email: 收件人邮箱地址
        code: 验证码字符串
        subject: 邮件主题（可选），默认为"验证码"
        body_template: 邮件正文模板（可选），默认为"您的验证码是：{code}"
        
    Returns:
        bool: 邮件发送成功返回True，失败返回False
        
    Example:
        >>> send_email("user@example.com", "123456")
        True
        >>> send_email("user@example.com", "123456", subject="注册验证码")
        True
        
    Note:
        - 使用SMTP_SSL加密连接
        - 自动重试最多3次
        - 连接超时时间为30秒
        - 失败时会记录错误日志
    """
    # 默认主题和正文
    if subject is None:
        subject = "验证码"
    if body_template is None:
        body_template = "您的验证码是：{code}"
    
    # 构建邮件内容
    body = body_template.format(code=code)
    sender_email = emailconfig.MAIL_ADDRESS
    sender_password = emailconfig.MAIL_PASSWORD
    
    # 检查配置
    if not sender_email or not sender_password:
        logger.error("❌ 邮件配置不完整：MAIL_ADDRESS或MAIL_PASSWORD未设置")
        return False
    
    # 创建邮件消息
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))
    
    # 重试机制
    for attempt in range(1, MAX_RETRY + 1):
        try:
            logger.info(f"📧 尝试发送邮件 ({attempt}/{MAX_RETRY}): {to_email}")
            
            # 创建SMTP连接（带超时）
            server = smtplib.SMTP_SSL(
                emailconfig.MAIL_SERVER, 
                emailconfig.MAIL_PORT,
                timeout=SMTP_TIMEOUT
            )
            
            # 登录并发送
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, message.as_string())
            server.quit()
            
            logger.info(f"✅ 邮件发送成功: {to_email}")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"❌ SMTP认证失败: {str(e)}")
            return False  # 认证失败不重试
            
        except smtplib.SMTPConnectError as e:
            logger.error(f"❌ SMTP连接失败: {str(e)}")
            if attempt < MAX_RETRY:
                logger.info(f"⏳ 等待重试...")
                continue
            return False
            
        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"❌ 收件人拒绝: {str(e)}")
            return False  # 收件人错误不重试
            
        except smtplib.SMTPException as e:
            logger.error(f"❌ SMTP错误 (尝试 {attempt}/{MAX_RETRY}): {str(e)}")
            if attempt < MAX_RETRY:
                logger.info(f"⏳ 等待重试...")
                continue
            return False
            
        except Exception as e:
            logger.error(f"❌ 邮件发送未知错误: {type(e).__name__}: {str(e)}")
            if attempt < MAX_RETRY:
                logger.info(f"⏳ 等待重试...")
                continue
            return False
    
    logger.error(f"❌ 邮件发送失败，已重试{MAX_RETRY}次: {to_email}")
    return False