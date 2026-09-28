"""推送通知（OneSignal Web Push）数据模型

三条链路为什么都要建表：

1. `push_subscriptions` —— OneSignal 侧用 `external_id` 关联我方 `user_id`，
   但**解绑与统计必须落到每条订阅**：同一用户可能有手机浏览器 + 电脑浏览器多个
   订阅，登出时若不按 `subscription_id` 精确解除，旧设备会继续收到推送（隐私问题）。
   本表同时预留 `platform`（web/miniapp/app）——后续接小程序或 App 时不需要改结构，
   只多一种 platform 取值，发送链路与偏好过滤逻辑复用。

2. `push_prefs` —— 用户必须能逐场景关掉推送（学习提醒/私信/公告/成绩）。
   推送是**打扰型**能力，缺了偏好开关等于把用户往「浏览器层直接屏蔽所有通知」推，
   一旦如此，今后任何推送都送不到，且我方无从感知。

3. `push_logs` —— 既做发送审计（谁在什么时候收到了什么），
   也用 `dedup_key` 唯一索引实现「同一事件同一用户当天只发一次」的幂等：
   定时提醒任务重跑、接口重试都不会造成重复打扰。

`dedup_key` 必须**可空**：MySQL 唯一索引允许多个 NULL，但只允许一个空串 ——
即时推送（IM 私信、后台群发）不参与去重，写 NULL；否则第二条即时推送就会撞唯一键。
同理，补列/建表时不能给 DEFAULT ''。

字段长度按「够用且不浪费」取：标题 120、正文 500（推送正文本身有平台长度上限，
超长会被 OneSignal 截断，与其在库里存超长内容不如入口就限制）。
"""
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, Index, Integer, String)

from ..database import Base


class PushSubscription(Base):
    """推送订阅（一个浏览器/设备一条；OneSignal subscription_id 唯一）"""
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        Index("ux_push_subscription_sid", "subscription_id", unique=True),
        Index("ix_push_subscription_user", "user_id", "revoked_at"),
        {"comment": "推送订阅：用户在各设备/浏览器的 OneSignal 订阅（external_id=users.user_id）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, comment="用户 ID（与 OneSignal external_id 一致）")
    subscription_id = Column(String(64), nullable=False, comment="OneSignal 订阅 ID（唯一）")
    # 平台：web=浏览器 Web Push / miniapp=微信小程序 / app=原生应用。
    # 当前只实现 web，但发送链路按平台无关设计，后续接小程序无需改表。
    platform = Column(String(20), default="web", comment="平台：web/miniapp/app")
    channel = Column(String(20), default="push", comment="通道：push/email/sms（预留）")
    device_type = Column(String(20), default="", comment="设备类型：Desktop/Mobile/Tablet")
    browser = Column(String(40), default="", comment="浏览器标识（Chrome/Safari/WeChat…）")
    user_agent = Column(String(255), default="", comment="原始 UA（排查用）")
    # opted_in=False 表示用户在浏览器层关闭了通知权限，但仍保留记录：
    # 再次开启时用同一 subscription_id 复用，避免重复行。
    opted_in = Column(Boolean, default=True, comment="是否已授权接收推送")
    created_at = Column(DateTime, default=datetime.now, comment="首次订阅时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    last_seen_at = Column(DateTime, default=datetime.now, comment="最近一次上报时间（判活跃设备）")
    revoked_at = Column(DateTime, nullable=True, comment="解绑时间（非空=已失效，不再推送）")


class PushPref(Base):
    """推送偏好（每用户一行；缺行视为「全部开启」，避免注册时要写一行）"""
    __tablename__ = "push_prefs"
    __table_args__ = (
        Index("ux_push_pref_user", "user_id", unique=True),
        {"comment": "推送偏好：用户逐场景开关（缺行=全开）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), nullable=False, comment="用户 ID")
    # 四类场景开关（与后端 PushEvent 常量一一对应）
    enable_study = Column(Boolean, default=True, comment="学习提醒：作业/打卡/复习")
    enable_im = Column(Boolean, default=True, comment="私信离线提醒")
    enable_announce = Column(Boolean, default=True, comment="公告与站内信")
    enable_exam = Column(Boolean, default=True, comment="考试与成绩通知")
    # 免打扰时段（HH:MM，两端都为空表示不启用）。
    # 不复用平台的 quiet_hours：那是「未成年人护眼宵禁」（会拦截接口），
    # 而这里是「成人/家长自愿的免打扰」，语义不同，混合会互相干扰。
    quiet_start = Column(String(5), default="", comment="免打扰开始（HH:MM，空=不启用）")
    quiet_end = Column(String(5), default="", comment="免打扰结束（HH:MM，空=不启用）")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")


class PushLog(Base):
    """推送发送记录（审计 + dedup_key 幂等去重）"""
    __tablename__ = "push_logs"
    __table_args__ = (
        Index("ux_push_log_dedup", "dedup_key", unique=True),
        Index("ix_push_log_user_time", "user_id", "created_at"),
        Index("ix_push_log_event_time", "event", "created_at"),
        {"comment": "推送发送记录：审计 + 幂等去重（dedup_key 可空）"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True, comment="主键自增")
    user_id = Column(String(64), default="", comment="接收用户（群发记 broadcast 时为接收方）")
    event = Column(String(30), default="", comment="事件：study/im/announce/exam/broadcast/test")
    title = Column(String(120), default="", comment="推送标题")
    body = Column(String(500), default="", comment="推送正文")
    url = Column(String(500), default="", comment="点击跳转地址")
    # 可空、无默认 —— 见模块 docstring（唯一索引只允许一个 NULL）
    dedup_key = Column(String(120), nullable=True, comment="幂等键（同键只发一次；空=不去重）")
    onesignal_id = Column(String(64), default="", comment="OneSignal 消息 ID（无订阅者时为空）")
    recipients = Column(Integer, default=0, comment="触达订阅数（OneSignal 返回）")
    ok = Column(Boolean, default=False, comment="是否发送成功")
    http_status = Column(Integer, default=0, comment="HTTP 状态码（0=未发起/异常）")
    error = Column(String(255), default="", comment="失败原因（截断存储）")
    created_at = Column(DateTime, default=datetime.now, comment="发送时间")
