-- ============================================================================
-- 商城商品初始化数据（products + product_benefits）
-- 对应迁移 056 / S4-M1；让后台「充值订单 → 商品管理」页有初始数据可展示
--
-- 用法（线上库）：
--   mysql -u<user> -p schoolexam < db/seed_commerce_products.sql
--
-- 特性：
--   1. 幂等 —— 按 sku 反连接判重，可反复执行，不会重复插入
--   2. 金额单位统一为「分」（DB-01 铁律，禁止 Float）
--   3. status 默认置为 online（上架），否则后台列表筛选「已上架」看不到
-- ============================================================================

SET NAMES utf8mb4;

-- ---------------------------------------------------------------------------
-- 一、商品（products）
-- ---------------------------------------------------------------------------
INSERT INTO products
  (sku, name, type, subtitle, description,
   price_fen, original_fen, duration_days, grade_scope,
   sort_order, status, online_at, created_by, updated_by, created_at)
SELECT t.sku, t.name, t.type, t.subtitle, t.description,
       t.price_fen, t.original_fen, t.duration_days, t.grade_scope,
       t.sort_order, t.status, NOW(), 'system', 'system', NOW()
FROM (
  -- ── 钻石充值 ──
  SELECT 'DIAMOND_60'   AS sku, '60 钻石'    AS name, 'diamond' AS type,
         '入门小额，随充随用' AS subtitle, '钻石可用于 AI 批改、AI 出题、AI 讲解等按次消耗场景。' AS description,
         600   AS price_fen, 600   AS original_fen, 0 AS duration_days,
         '' AS grade_scope, 100 AS sort_order, 'online' AS status
  UNION ALL SELECT 'DIAMOND_300',  '300 钻石',  'diamond', '常用档位，够用一个月',
         '钻石可用于 AI 批改、AI 出题、AI 讲解等按次消耗场景。',
         3000,  3000,  0, '', 110, 'online'
  UNION ALL SELECT 'DIAMOND_680',  '680 钻石',  'diamond', '热销档位，多送 80 钻',
         '钻石可用于 AI 批改、AI 出题、AI 讲解等按次消耗场景。',
         6800,  7500,  0, '', 120, 'online'
  UNION ALL SELECT 'DIAMOND_1280', '1280 钻石', 'diamond', '囤量档位，多送 280 钻',
         '钻石可用于 AI 批改、AI 出题、AI 讲解等按次消耗场景。',
         12800, 15000, 0, '', 130, 'online'

  -- ── 会员（membership）──
  UNION ALL SELECT 'VIP_MONTH',   '月度会员',  'membership', '30 天全站权益',
         '会员期内：AI 批改不限次、专属题库、去广告、家长报告周报。',
         3000,  3000,  30,  '', 200, 'online'
  UNION ALL SELECT 'VIP_QUARTER', '季度会员',  'membership', '90 天，折合每月 26 元',
         '会员期内：AI 批改不限次、专属题库、去广告、家长报告周报。',
         7800,  9000,  90,  '', 210, 'online'
  UNION ALL SELECT 'VIP_YEAR',    '年度会员',  'membership', '365 天，折合每月不到 25 元',
         '会员期内：AI 批改不限次、专属题库、去广告、家长报告周报。',
         29800, 36000, 365, '', 220, 'online'

  -- ── 补签卡（coupon）──
  UNION ALL SELECT 'MAKEUP_5',     '补签卡 ×5', 'coupon', '漏打卡也能补',
         '用于补签每日打卡任务，每张可补 1 次。',
         500,   500,   0,  '', 300, 'online'

  -- ── 组合包（bundle）──
  UNION ALL SELECT 'BUNDLE_VIP_DIAMOND', '年卡 + 680 钻石', 'bundle', '一次搞定会员与钻石',
         '年度会员 365 天 + 680 钻石，比单买省 38 元。',
         32800, 36600, 365, '', 400, 'online'
) AS t
WHERE NOT EXISTS (
  SELECT 1 FROM products p WHERE p.sku = t.sku
);

-- ---------------------------------------------------------------------------
-- 二、商品权益模板（product_benefits）
--     benefit_type: vip_days / diamond / coupon / ai_quota
--     benefit_key : coupon 类型（makeup_card）等
-- ---------------------------------------------------------------------------

-- 钻石类：sku → 钻石数量
INSERT INTO product_benefits (product_id, benefit_type, benefit_key, amount, sort_order, created_at)
SELECT p.id, 'diamond', '', t.amount, 0, NOW()
FROM products p
JOIN (
  SELECT 'DIAMOND_60' AS sku, 60 AS amount
  UNION ALL SELECT 'DIAMOND_300',  300
  UNION ALL SELECT 'DIAMOND_680',  680
  UNION ALL SELECT 'DIAMOND_1280', 1280
) AS t ON t.sku = p.sku
WHERE NOT EXISTS (
  SELECT 1 FROM product_benefits b
  WHERE b.product_id = p.id AND b.benefit_type = 'diamond' AND b.amount = t.amount
);

-- 会员类：sku → 会员天数
INSERT INTO product_benefits (product_id, benefit_type, benefit_key, amount, sort_order, created_at)
SELECT p.id, 'vip_days', '', t.amount, 0, NOW()
FROM products p
JOIN (
  SELECT 'VIP_MONTH' AS sku, 30 AS amount
  UNION ALL SELECT 'VIP_QUARTER', 90
  UNION ALL SELECT 'VIP_YEAR',    365
) AS t ON t.sku = p.sku
WHERE NOT EXISTS (
  SELECT 1 FROM product_benefits b
  WHERE b.product_id = p.id AND b.benefit_type = 'vip_days' AND b.amount = t.amount
);

-- 补签卡：sku → coupon(makeup_card) × 5
INSERT INTO product_benefits (product_id, benefit_type, benefit_key, amount, sort_order, created_at)
SELECT p.id, 'coupon', 'makeup_card', 5, 0, NOW()
FROM products p
WHERE p.sku = 'MAKEUP_5'
  AND NOT EXISTS (
    SELECT 1 FROM product_benefits b
    WHERE b.product_id = p.id AND b.benefit_type = 'coupon' AND b.benefit_key = 'makeup_card'
  );

-- 组合包：年卡 + 680 钻石（两条权益）
INSERT INTO product_benefits (product_id, benefit_type, benefit_key, amount, sort_order, created_at)
SELECT p.id, 'vip_days', '', 365, 0, NOW()
FROM products p
WHERE p.sku = 'BUNDLE_VIP_DIAMOND'
  AND NOT EXISTS (
    SELECT 1 FROM product_benefits b
    WHERE b.product_id = p.id AND b.benefit_type = 'vip_days' AND b.amount = 365
  );

INSERT INTO product_benefits (product_id, benefit_type, benefit_key, amount, sort_order, created_at)
SELECT p.id, 'diamond', '', 680, 1, NOW()
FROM products p
WHERE p.sku = 'BUNDLE_VIP_DIAMOND'
  AND NOT EXISTS (
    SELECT 1 FROM product_benefits b
    WHERE b.product_id = p.id AND b.benefit_type = 'diamond' AND b.amount = 680
  );

-- ---------------------------------------------------------------------------
-- 三、结果核对（执行后打印，便于人工确认）
-- ---------------------------------------------------------------------------
SELECT p.sku            AS 商品编码,
       p.name           AS 名称,
       p.type           AS 类型,
       p.price_fen / 100 AS 售价元,
       p.original_fen / 100 AS 原价元,
       p.status         AS 状态,
       (SELECT COUNT(*) FROM product_benefits b WHERE b.product_id = p.id) AS 权益数
FROM products p
ORDER BY p.sort_order;
