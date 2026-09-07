# 智学学堂 · 优化方案与功能设计 PRD（v2 更新）

> 配套 `00-总纲.md`、`01-产品优化方案.md`、`06-PRD产品需求文档.md`。
> 本文是 **2026-09-07 的代码现状更新版**，反映 S1-R 模块拆分后的最新架构与数据。
> 编制日期：2026-09-07 · 版本 v2.0 · 现状数据为代码实测

---

## 0. 文档信息

| 项 | 内容 |
|---|---|
| 文档名称 | 优化方案与功能设计 PRD（v2 更新） |
| 版本 | v2.0 |
| 编制日期 | 2026-09-07 |
| 上游文档 | `00-总纲.md`、`01-产品优化方案.md`、`06-PRD产品需求文档.md` |
| 数据口径 | 代码实测（426 端点 / 86 表 / 65 迁移 / 268 测试 / 9 域） |
| 与 v1 的差异 | v1（2026-09-02）基于 377 端点 / 85 表 / 56 迁移 / 124 测试；v2 反映 S1-R 模块拆分、S2-S4 商城、S6 教材版本等后续迭代的实际落地 |

---

## 1. 现状体检（v2 更新）

### 1.1 核心指标对比

| 维度 | v1（09-02） | v2（09-07） | 变化 |
|---|---:|---:|---|
| HTTP 端点 | 377 | **426** | +49（商城 + 区域 + RBAC + 审核 + 审计） |
| ORM 模型文件 | 40 | **46** | +6（commerce_product/order/diamond/makeup_card 等） |
| 数据库表 | 85 | **86** | +1（schema_migrations 迁移版本表） |
| 迁移脚本 | 56 | **65** | +9（053-061 区域/教材/RBAC/审计/商城/商品/订单/VIP 到期） |
| 自动化测试 | 124 用例 / 20 文件 | **268 用例 / 39 文件** | **+144 用例**（商城、履约、VIP、管理 API、地理等） |
| 域数 | 0（单体路由） | **9** | S1-R 完成九域拆分 |
| `appOptions.js` | 3,643 行 | 3,643 行 | 未变（待设置页整理任务拆分） |

### 1.2 九域架构（S1-R 已落地）

| 域 | 代号 | 职责 | 核心表 |
|---|---|---|---|
| D1 identity | 身份 | 注册/登录/Token/家长密码 | `users` `parent_passwords` |
| D2 engagement | 学习 | 每日任务/背诵/听写/专注/补签卡 | `daily_tasks` `vocab_progress` `makeup_usage_logs` |
| D3 assessment | 测评 | 出卷/判分/错题/申诉 | `exam_attempts` `wrong_records` `answer_appeals` |
| D4 engine | 引擎 | 出题/数学生成/内容采集 | `questions` `paper_questions` `middle_questions` |
| D5 family | 家庭 | 家长管理/留言/周报/申诉 | `parent_messages` `weekly_reports` `wish_items` |
| D6 platform | 平台 | AI 服务/配置/系统管理 | `ai_usage_logs` `system_config` |
| D7 commerce | 商城 | 商品/订单/支付/钻石/履约 | `products` `orders` `pay_transactions` `diamond_accounts` |
| D8 content | 内容 | 教材版本/区域/知识点 | `textbook_versions` `regions` |
| D9 frozen | 冻结 | IM + 账本（配置可关闭） | `db_im_*` `db_ledger_*` |

**架构护栏**：
- `.importlinter` Contract 1 = 九域 independence（互不 import）
- 跨域调用仅允许经 `contracts.py`（PEP 562 延迟再导出）
- Contract 2 = D9 frozen 密封
- `lint-imports` 实测 2 kept / 0 broken（336 文件 / 1021 依赖）

### 1.3 已完成的关键迭代

| 迭代 | 内容 | 端点增量 | 测试增量 |
|---|---|---|---|
| S1 核心 | 九域拆分 + 契约收口 + 静态护栏 | 0（搬迁） | 0 |
| S1-R 修订 | D8 数据归属修正 + admin 域补全 | 0 | 0 |
| S2 M1-M4 | 商城商品/订单/支付/履约 | +30 | +80 |
| S3 M1-M5 | RBAC + 审计 + 内容审核 | +12 | +40 |
| S4 M1-M5 | 用户端商城 + VIP 到期 + 履约测试 | +5 | +60 |
| S6 | 教材版本 + 区域 + 地理位置 | +4 | +20 |

### 1.4 仍存在的致命缺口（对照 00-总纲 §2.2）

| 缺口 | v1 状态 | v2 状态 | 变化 |
|---|---|---|---|
| 支付/订单/订阅 | 0 端点 | **已有完整 commerce 域** | ✅ 已补齐（人工支付网关版） |
| VIP 到期管理 | 无 expire_at | **迁移 071 已加列** | ✅ 已补齐 |
| 履约服务 | 无 | **fulfillment.py 已实现** | ✅ 已补齐 |
| RBAC 权限点 | 无 | **admin_permissions + role_permissions** | ✅ 已补齐 |
| 操作审计 | 基础 | **扩展 ip/ua/amount_fen/target_type/extra_json** | ✅ 已增强 |
| 掌握度模型 | 无 | **无** | 🔴 未动 |
| 合规底座 | 无 | **无** | 🔴 未动 |
| 可观测性 | 无 | **无** | 🔴 未动 |
| IM/账本冻结 | 未隔离 | **已迁至 D9 frozen 域 + 配置开关** | ✅ 已隔离 |
| 测试覆盖 | 124 用例 | **268 用例** | 🟢 翻倍 |

---

## 2. 优化方案（v2 优先级重排）

> 基于 v2 现状，原 `01-产品优化方案.md` 的 M0 筑基已有约 60% 完成。以下是**剩余未完成项**的优先级重排。

### 2.1 当前优先级矩阵

| 优先级 | 需求 | 原编号 | 当前状态 | 预估工作量 |
|:--:|---|---|---|---|
| **P0** | 掌握度模型 v1 | M0-1 | 🔴 未启动 | 3-4 周 |
| **P0** | 合规底座 | M0-3 | 🔴 未启动 | 2-3 周 |
| **P0** | 可观测性 | M0-4 | 🔴 未启动 | 1-2 周 |
| **P0** | 测试补齐 + CI | M0-6 | 🟡 268 用例但无 CI 卡点 | 1 周 |
| P1 | 诊断测评 | M1-1 | 🔴 依赖掌握度 | 2-3 周 |
| P1 | 个性化学习路径 | M1-2 | 🔴 依赖掌握度 | 3-4 周 |
| P1 | AI 讲题升级 | M1-3 | 🔴 未启动 | 2-3 周 |
| P1 | 家长学情中心 | M1-4 | 🔴 未启动 | 2 周 |
| P1 | AI 成本治理 | M1-7 | 🟡 三链路已有，缺缓存/评测/看板 | 2 周 |
| P2 | 内容生产流水线 | M1-5 | 🔴 未启动 | 3 周 |
| P2 | 运营后台增强 | M1-6 | 🟡 基础已有，缺活动/推送 | 2 周 |

### 2.2 近期可执行优化项（不依赖大团队）

#### 2.2.1 设置页与家长管理页整理（已排期）

**现状问题**：
- `SettingsView.vue` 363 行，家长卡在 `parentPhase==='open'` 下平铺 15 个 `pc-sec` 区块
- `appOptions.js` 3,643 行单 mixin，所有逻辑集中
- 留言与周报寄语语义重叠、两处学习数据口径不同
- 假「检查更新」按钮

**方案**：
1. 家长管理独立成 `tab='parent'`（新 `ParentView.vue`）
2. 抽 `logic/parent.js`（parentData/parentComputed/parentMethods 三纯字典展开合并）
3. 5 个子组件（Todo/StudyConfig/Reward/Msg/Data）+ `<details>` 折叠
4. 扩展 `/api/parent/notices` 返回待办计数（不新建端点）
5. SettingsView 瘦身至 ~80 行

#### 2.2.2 用户端商城与支付闭环（已排期）

**现状问题**：
- 前端零处调用 `/api/commerce/*`（后端先行、前端未接）
- 开发库缺迁移 051-070，`products`/`orders` 表不存在
- 核销后无履约（`confirm_payment` 只到 PAID，无 FULFILLED 调用点）

**方案**：
1. 钱包页升级为商城（商品列表 + 订单 + 支付弹窗）
2. 客服独立成 tab「帮助与客服」
3. 全自动履约（fulfillment.py 消费 benefit_snapshot）
4. VIP 到期降级（迁移 071 已就绪）
5. 双收款码 + 客服二维码展示

#### 2.2.3 可观测性（建议下一步）

**功能设计**：

| 编号 | 功能 | 实现方式 |
|---|---|---|
| OBS-01 | request-id 全链路 | FastAPI 中间件生成 UUID，注入 `state`，响应头返回 `X-Request-Id` |
| OBS-02 | 结构化日志 | Python `logging` JSON formatter，统一字段：`ts/level/request_id/user_id/method/path/status/duration_ms` |
| OBS-03 | 健康检查增强 | `/health` 检查 DB 连接 + Redis（如有）+ 迁移版本，返回 `{status, db, migrations, uptime}` |
| OBS-04 | 核心指标端点 | `/api/metrics` 返回 Prometheus 格式或 JSON：DAU/答题量/AI 调用量/接口 P95/错误率 |
| OBS-05 | 慢查询日志 | SQLAlchemy event 监听，> 500ms 的查询记录 warning 日志 |
| OBS-06 | 告警 | P0 级（服务不可用/DB 连接失败/错误率 > 5%）→ 邮件/webhook 通知 |

#### 2.2.4 VIP 到期过滤（已完成 ✅）

**变更**：`_load_vip_users()` SQL 从 `SELECT user_id FROM vip_users` 改为 `WHERE expire_at IS NULL OR expire_at > NOW()`

**影响**：已到期 VIP 自动降级为免费用户，无法访问付费链（DeepSeek）

**测试**：`tests/test_ai_vip.py` 18 用例全绿（SQL 过滤 / 缓存 / 链路组合 / 门控）

---

## 3. 功能设计：掌握度模型 v1（P0 核心）

> 对应 `06-PRD §5.1`，此处给出**基于当前代码的具体实现方案**。

### 3.1 数据模型

```sql
-- 知识点树（新增表）
CREATE TABLE knowledge_points (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    subject     VARCHAR(20) NOT NULL,     -- math/chinese/english/physics/...
    grade       TINYINT NOT NULL,         -- 1-9
    unit        VARCHAR(100),             -- 单元名
    name        VARCHAR(200) NOT NULL,    -- 知识点名
    parent_id   INT NULL,                 -- 层级依赖
    sort_order  INT DEFAULT 0,
    UNIQUE KEY (subject, grade, name)
);

-- 题目-知识点映射（新增表）
CREATE TABLE question_kp_map (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    question_id     INT NOT NULL,         -- 对应 questions.id / middle_questions.id
    question_type   VARCHAR(30) NOT NULL, -- 'primary' / 'middle'
    kp_id           INT NOT NULL,         -- 对应 knowledge_points.id
    weight          FLOAT DEFAULT 1.0,    -- 主知识点 1.0 / 副知识点 0.5
    UNIQUE KEY (question_id, question_type, kp_id)
);

-- 掌握度记录（新增表）
CREATE TABLE mastery_records (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         VARCHAR(50) NOT NULL,
    kp_id           INT NOT NULL,
    mastery         FLOAT NOT NULL,       -- 0-100
    sample_count    INT DEFAULT 0,        -- 样本量（置信度）
    last_answer_at  DATETIME,
    calculated_at   DATETIME NOT NULL,
    UNIQUE KEY (user_id, kp_id)
);

-- attempt_answers 加列（迁移）
ALTER TABLE attempt_answers ADD COLUMN duration_ms INT DEFAULT NULL
    COMMENT '每题作答用时（毫秒）';
```

### 3.2 计算引擎

```python
# app/domains/engine/services/mastery.py

def calculate_mastery(db, user_id: str, kp_id: int) -> float:
    """基于答题记录计算单知识点掌握度（幂等）"""
    # 1. 取该知识点关联的题目 ID 列表
    question_ids = get_kp_question_ids(db, kp_id)
    
    # 2. 取用户近 N=10 次作答记录（含正确率、用时）
    attempts = get_recent_attempts(db, user_id, question_ids, limit=10)
    
    # 3. 计算各因子
    C = correct_rate(attempts)                    # 正确率
    T = time_ratio(attempts, kp_avg_time)         # 用时比
    R = recency_decay(attempts, lambda_=14)       # 时效性
    D = difficulty_weight(attempts)               # 难度权重
    S = streak_bonus(attempts)                    # 连续正确加分
    
    # 4. 合成
    C_adj = C * (0.7 + 0.3 * clamp(T, 0.5, 1.5))
    base = 100 * C_adj * D
    mastery = clamp(base * R + 100 * (1 - R) * 20 + S * R, 0, 100)
    
    return round(mastery, 1)
```

### 3.3 接口设计

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/mastery/user/{user_id}` | GET | 用户全量掌握度（按学科/年级分组） |
| `/api/mastery/user/{user_id}/kp/{kp_id}` | GET | 单知识点掌握度 + 计算依据 |
| `/api/mastery/user/{user_id}/heatmap` | GET | 热力图数据（学科 × 知识点二维矩阵） |
| `/api/mastery/user/{user_id}/trend` | GET | 掌握度趋势（近 30 天快照） |
| `/api/admin/mastery/recalculate` | POST | 管理员触发全量重算 |

### 3.4 前置依赖

| 依赖 | 状态 | 说明 |
|---|---|---|
| 知识点树数据 | 🔴 缺失 | 需教研建设小学三科 + 初中九科知识点树 |
| 题目-知识点标注 | 🔴 缺失 | 存量题目标注率 < 10%，需 AI 预标注 + 教研抽检 |
| attempt_answers.duration_ms | 🔴 缺失 | 需迁移加列 + 前端采集每题用时 |

---

## 4. 功能设计：合规底座（P0）

### 4.1 核心功能

| 编号 | 功能 | 实现要点 |
|---|---|---|
| CMP-01 | 儿童个人信息处理规则 | 独立页面，注册/首次使用时强制阅读并同意 |
| CMP-02 | 监护人同意流程 | 勾选 + 记录 `guardian_consent_at` + 规则版本号 + IP/UA |
| CMP-03 | 年龄识别 | 注册时采集出生年份，< 14 岁走儿童信息处理流程 |
| CMP-04 | 内容安全过滤 | AI 输出过安全过滤层（敏感词 + 兜底模板） |
| CMP-05 | AI 生成标识 | AI 输出在前端显著标识「AI 生成」 |
| CMP-06 | 数据导出/删除 | 用户可申请导出（JSON）与删除个人数据 |

### 4.2 数据模型

```sql
-- 监护人同意记录（新增表）
CREATE TABLE guardian_consents (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         VARCHAR(50) NOT NULL,
    guardian_name   VARCHAR(100),
    consent_at      DATETIME NOT NULL,
    rule_version    VARCHAR(20) NOT NULL,
    ip_address      VARCHAR(45),
    user_agent      TEXT,
    revoked_at      DATETIME NULL,
    UNIQUE KEY (user_id, rule_version)
);
```

---

## 5. 功能设计：可观测性（P0）

### 5.1 实现方案

```python
# app/middleware/request_id.py
import uuid
from starlette.middleware.base import BaseHTTPMiddleware

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response
```

### 5.2 健康检查增强

```python
# app/main.py /health 端点增强
@app.get("/health")
def health(db: Session = Depends(get_db)):
    checks = {"status": "ok", "checks": {}}
    # DB 连接检查
    try:
        db.execute(text("SELECT 1"))
        checks["checks"]["db"] = "ok"
    except Exception as e:
        checks["checks"]["db"] = f"error: {e}"
        checks["status"] = "degraded"
    # 迁移版本检查
    try:
        row = db.execute(text("SELECT MAX(version) FROM schema_migrations")).first()
        checks["checks"]["migrations"] = row[0] if row else "none"
    except:
        checks["checks"]["migrations"] = "unknown"
    checks["checks"]["uptime_sec"] = time.time() - _start_time
    return checks
```

---

## 6. 指标体系（v2 更新）

### 6.1 北极星指标

> **周活跃 learning 用户的知识点掌握度提升量**

### 6.2 当前可采集指标（基于现有端点）

| 指标 | 来源 | 采集方式 |
|---|---|---|
| DAU | `/api/auth/login` | 按 user_id 去重日登录数 |
| 日答题量 | `/api/exam/submit` | 日提交次数 |
| AI 调用量 | `ai_usage_logs` 表 | 已有，按 provider/model 分组 |
| AI 成本 | `ai_usage_logs.tokens` | 按模型单价估算 |
| 家长活跃度 | `/api/parent/*` | 日调用家长接口去重 user_id |
| 商品浏览量 | `/api/commerce/products` | 日 GET 次数（待加埋点） |
| 订单创建量 | `/api/commerce/orders` | 日创建订单数（已有） |

### 6.3 待建设指标

| 指标 | 依赖 | 优先级 |
|---|---|---|
| 掌握度分布 | 掌握度模型 | P0 |
| 知识点覆盖率 | 题目标注 | P0 |
| 付费转化率 | 商城 + 订单 | P1（商城上线后可采集） |
| 诊断完成率 | 诊断测评 | P1 |
| 讲解满意度 | AI 讲题升级 | P2 |

---

## 7. 风险清单（v2 更新）

| 风险 | 影响 | 当前状态 | 应对 |
|---|---|---|---|
| 掌握度模型不准 | 推荐失灵 | 🔴 未启动 | 先离线回测 → 小流量实验 → 全量 |
| 合规处罚 | 下架/罚款 | 🔴 未启动 | 优先建监护人同意 + 内容安全 |
| AI 供应商单点 | 服务不可用 | 🟡 三链路但免费链耗尽 | 补缓存 + 配额 + 降级方案 |
| 内容质量事故 | 信任崩塌 | 🟡 有申诉机制但无抽检 | 建抽检队列 + 申诉驱动复核 |
| appOptions.js 单点 | 改动波及全局 | 🟡 3,643 行未拆分 | 设置页整理任务已开始拆分 |
| 无 CI 卡点 | 合并质量不可控 | 🟡 268 用例但无 CI | 建 CI 流水线 + 覆盖率门禁 |
| 人工核销出错 | 资金损失 | 🟡 后台已有但缺审批流 | 补大额审批 + 日报 + 权限互斥 |

---

## 8. 与 v1 文档的对照

| v1 文档 | v2 对应 | 变化说明 |
|---|---|---|
| `01-产品优化方案.md` §二 M0 筑基 | 本文 §2.1 | M0-2（交易）/ M0-5（冻结）已完成，M0-1/3/4/6 待做 |
| `06-PRD §5.1` 掌握度模型 | 本文 §3 | 补充了基于当前代码的具体实现方案 |
| `06-PRD §5.2` 交易体系 | 已完成 | commerce 域 426 端点中约占 30+，履约已实现 |
| `06-PRD §5.3` 合规底座 | 本文 §4 | 未变，仍为 P0 |
| `06-PRD §5.4` 可观测性 | 本文 §5 | 补充了具体实现代码 |
| `00-总纲 §2.2` 致命缺口 | 本文 §1.4 | 支付/RBAC/审计/冻结已补齐，掌握度/合规/可观测仍缺 |

---

## 9. 下一步行动

1. **掌握度模型 v1**（P0，3-4 周）：知识点树建设 → 题目标注 → 计算引擎 → 查询接口
2. **合规底座**（P0，2-3 周）：监护人同意 → 内容安全 → AI 标识 → 数据导出
3. **可观测性**（P0，1-2 周）：request-id → 结构化日志 → 健康检查增强 → 指标端点
4. **CI 流水线**（P0，1 周）：GitHub Actions / GitLab CI + 覆盖率门禁 + lint-imports
5. **AI 成本治理**（P1，2 周）：语义缓存 → 回归评测集 → 成本看板
