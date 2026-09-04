-- ============================================================
-- 教材版本默认数据初始化（省级主流版本 → region 映射）
-- ============================================================
-- 版本选择优先级（app/domains/content/routers/textbook.py::resolve_textbook_id）：
--   用户自选 → 本省版本（region = 省份代码，即 chinaAdminCode 前 2 位）
--            → 全国通用（region = ''）
--
-- 幂等：按 (subject, grade, region, name) 判重，已有行不重复插入，可反复执行。
-- 前置条件：textbook_versions.region 列已存在（迁移 061，deploy.sh 自动执行）。
-- 导入方式（线上服务器执行）：
--   mysql -u<user> -p schoolexam < db/seed_textbook_versions.sql
--
-- 映射依据：全国义务教育阶段教材主流使用情况——语文 2019 年起全国统一统编版；
-- 各省差异主要在数学与英语。教材实际以地市为单位选用，本表为省级主流版本，
-- 仅作默认推荐；用户可在前端 /api/textbook/versions 自行切换版本。
--
-- 省份代码：11=北京 12=天津 31=上海 32=江苏 33=浙江 37=山东
-- ============================================================

-- ── 0) 存量修正：原 G7 数学「浙教版」建表时未区分地区（region=''），
--       改为浙江专用（region='33'），让其他省份回退到下方全国默认人教版 ──
UPDATE textbook_versions
SET region = '33'
WHERE subject = '数学' AND grade = 7 AND name = '浙教版' AND region = '';

-- ── 1) 默认数据（全国通用 + 省级主流），缺失才插入 ──
INSERT INTO textbook_versions (subject, grade, name, sort_order, enabled, region, remark, created_at)
SELECT v.subject, v.grade, v.name, 0, 1, v.region, v.remark, NOW()
FROM (
    -- ── 全国通用默认（region = ''）──
    SELECT '语文' AS subject, 1 AS grade, '统编版' AS name, '' AS region, '部编版，全国统一' AS remark
    UNION ALL SELECT '语文', 2, '统编版', '', '部编版，全国统一'
    UNION ALL SELECT '语文', 3, '统编版', '', '部编版，全国统一'
    UNION ALL SELECT '语文', 4, '统编版', '', '部编版，全国统一'
    UNION ALL SELECT '语文', 5, '统编版', '', '部编版，全国统一'
    UNION ALL SELECT '语文', 6, '统编版', '', '部编版，全国统一'
    UNION ALL SELECT '语文', 7, '统编版', '', '部编版，全国统一'
    UNION ALL SELECT '语文', 8, '统编版', '', '部编版，全国统一'
    UNION ALL SELECT '语文', 9, '统编版', '', '部编版，全国统一'

    UNION ALL SELECT '数学', 1, '人教版', '', '全国主流版本'
    UNION ALL SELECT '数学', 2, '人教版', '', '全国主流版本'
    UNION ALL SELECT '数学', 3, '人教版', '', '全国主流版本'
    UNION ALL SELECT '数学', 4, '人教版', '', '全国主流版本'
    UNION ALL SELECT '数学', 5, '人教版', '', '全国主流版本'
    UNION ALL SELECT '数学', 6, '人教版', '', '全国主流版本'
    UNION ALL SELECT '数学', 7, '人教版', '', '全国主流版本'
    UNION ALL SELECT '数学', 8, '人教版', '', '全国主流版本'
    UNION ALL SELECT '数学', 9, '人教版', '', '全国主流版本'

    -- 英语全国默认：三年级起点（多数地区 G3 起开课），初中人教版
    UNION ALL SELECT '英语', 3, '人教版PEP', '', '三年级起点，全国主流'
    UNION ALL SELECT '英语', 4, '人教版PEP', '', '三年级起点，全国主流'
    UNION ALL SELECT '英语', 5, '人教版PEP', '', '三年级起点，全国主流'
    UNION ALL SELECT '英语', 6, '人教版PEP', '', '三年级起点，全国主流'
    UNION ALL SELECT '英语', 7, '人教版', '', '初中主流（新目标）'
    UNION ALL SELECT '英语', 8, '人教版', '', '初中主流（新目标）'
    UNION ALL SELECT '英语', 9, '人教版', '', '初中主流（新目标）'

    -- ── 北京（11）──
    UNION ALL SELECT '数学', 1, '北京版', '11', '北京市主流'
    UNION ALL SELECT '数学', 2, '北京版', '11', '北京市主流'
    UNION ALL SELECT '数学', 3, '北京版', '11', '北京市主流'
    UNION ALL SELECT '数学', 4, '北京版', '11', '北京市主流'
    UNION ALL SELECT '数学', 5, '北京版', '11', '北京市主流'
    UNION ALL SELECT '数学', 6, '北京版', '11', '北京市主流'
    UNION ALL SELECT '数学', 7, '北京版', '11', '北京市初中主流'
    UNION ALL SELECT '数学', 8, '北京版', '11', '北京市初中主流'
    UNION ALL SELECT '数学', 9, '北京版', '11', '北京市初中主流'
    UNION ALL SELECT '英语', 1, '北京版', '11', '北京市主流（一年级起点）'
    UNION ALL SELECT '英语', 2, '北京版', '11', '北京市主流（一年级起点）'
    UNION ALL SELECT '英语', 3, '北京版', '11', '北京市主流'
    UNION ALL SELECT '英语', 4, '北京版', '11', '北京市主流'
    UNION ALL SELECT '英语', 5, '北京版', '11', '北京市主流'
    UNION ALL SELECT '英语', 6, '北京版', '11', '北京市主流'
    UNION ALL SELECT '英语', 7, '北京版', '11', '北京市初中主流'
    UNION ALL SELECT '英语', 8, '北京版', '11', '北京市初中主流'
    UNION ALL SELECT '英语', 9, '北京版', '11', '北京市初中主流'

    -- ── 天津（12）──
    UNION ALL SELECT '英语', 1, '外研版（一年级起点）', '12', '天津市主流'
    UNION ALL SELECT '英语', 2, '外研版（一年级起点）', '12', '天津市主流'
    UNION ALL SELECT '英语', 3, '外研版（一年级起点）', '12', '天津市主流'
    UNION ALL SELECT '英语', 4, '外研版（一年级起点）', '12', '天津市主流'
    UNION ALL SELECT '英语', 5, '外研版（一年级起点）', '12', '天津市主流'
    UNION ALL SELECT '英语', 6, '外研版（一年级起点）', '12', '天津市主流'
    UNION ALL SELECT '英语', 7, '外研版', '12', '天津市初中主流'
    UNION ALL SELECT '英语', 8, '外研版', '12', '天津市初中主流'
    UNION ALL SELECT '英语', 9, '外研版', '12', '天津市初中主流'

    -- ── 上海（31）：五四学制（小学五年、初中四年，六年级=预初）──
    UNION ALL SELECT '数学', 1, '沪教版（五四制）', '31', '上海市主流'
    UNION ALL SELECT '数学', 2, '沪教版（五四制）', '31', '上海市主流'
    UNION ALL SELECT '数学', 3, '沪教版（五四制）', '31', '上海市主流'
    UNION ALL SELECT '数学', 4, '沪教版（五四制）', '31', '上海市主流'
    UNION ALL SELECT '数学', 5, '沪教版（五四制）', '31', '上海市主流'
    UNION ALL SELECT '数学', 6, '沪教版（五四制）', '31', '上海六年级=初中预初'
    UNION ALL SELECT '数学', 7, '沪教版（五四制）', '31', '上海市初中主流'
    UNION ALL SELECT '数学', 8, '沪教版（五四制）', '31', '上海市初中主流'
    UNION ALL SELECT '数学', 9, '沪教版（五四制）', '31', '上海市初中主流'
    UNION ALL SELECT '英语', 1, '沪教版（牛津上海版）', '31', '上海市主流（一年级起点）'
    UNION ALL SELECT '英语', 2, '沪教版（牛津上海版）', '31', '上海市主流（一年级起点）'
    UNION ALL SELECT '英语', 3, '沪教版（牛津上海版）', '31', '上海市主流'
    UNION ALL SELECT '英语', 4, '沪教版（牛津上海版）', '31', '上海市主流'
    UNION ALL SELECT '英语', 5, '沪教版（牛津上海版）', '31', '上海市主流'
    UNION ALL SELECT '英语', 6, '沪教版（牛津上海版）', '31', '上海六年级=初中预初'
    UNION ALL SELECT '英语', 7, '沪教版（牛津上海版）', '31', '上海市初中主流'
    UNION ALL SELECT '英语', 8, '沪教版（牛津上海版）', '31', '上海市初中主流'
    UNION ALL SELECT '英语', 9, '沪教版（牛津上海版）', '31', '上海市初中主流'

    -- ── 江苏（32）──
    UNION ALL SELECT '数学', 1, '苏教版', '32', '江苏省主流'
    UNION ALL SELECT '数学', 2, '苏教版', '32', '江苏省主流'
    UNION ALL SELECT '数学', 3, '苏教版', '32', '江苏省主流'
    UNION ALL SELECT '数学', 4, '苏教版', '32', '江苏省主流'
    UNION ALL SELECT '数学', 5, '苏教版', '32', '江苏省主流'
    UNION ALL SELECT '数学', 6, '苏教版', '32', '江苏省主流'
    UNION ALL SELECT '数学', 7, '苏科版', '32', '江苏省初中主流'
    UNION ALL SELECT '数学', 8, '苏科版', '32', '江苏省初中主流'
    UNION ALL SELECT '数学', 9, '苏科版', '32', '江苏省初中主流'
    UNION ALL SELECT '英语', 3, '译林版', '32', '江苏省主流（三年级起点）'
    UNION ALL SELECT '英语', 4, '译林版', '32', '江苏省主流'
    UNION ALL SELECT '英语', 5, '译林版', '32', '江苏省主流'
    UNION ALL SELECT '英语', 6, '译林版', '32', '江苏省主流'
    UNION ALL SELECT '英语', 7, '译林版', '32', '江苏省初中主流'
    UNION ALL SELECT '英语', 8, '译林版', '32', '江苏省初中主流'
    UNION ALL SELECT '英语', 9, '译林版', '32', '江苏省初中主流'

    -- ── 浙江（33）：小学数学/英语以人教版为主（回退全国默认），初中数学浙教版 ──
    UNION ALL SELECT '数学', 7, '浙教版', '33', '浙江省初中主流'
    UNION ALL SELECT '数学', 8, '浙教版', '33', '浙江省初中主流'
    UNION ALL SELECT '数学', 9, '浙教版', '33', '浙江省初中主流'

    -- ── 山东（37）──
    UNION ALL SELECT '数学', 1, '青岛版', '37', '山东多地主流（与人教版并用）'
    UNION ALL SELECT '数学', 2, '青岛版', '37', '山东多地主流（与人教版并用）'
    UNION ALL SELECT '数学', 3, '青岛版', '37', '山东多地主流（与人教版并用）'
    UNION ALL SELECT '数学', 4, '青岛版', '37', '山东多地主流（与人教版并用）'
    UNION ALL SELECT '数学', 5, '青岛版', '37', '山东多地主流（与人教版并用）'
    UNION ALL SELECT '数学', 6, '青岛版', '37', '山东多地主流（与人教版并用）'
    UNION ALL SELECT '英语', 3, '外研版（三年级起点）', '37', '山东主流（与人教PEP并用）'
    UNION ALL SELECT '英语', 4, '外研版（三年级起点）', '37', '山东主流（与人教PEP并用）'
    UNION ALL SELECT '英语', 5, '外研版（三年级起点）', '37', '山东主流（与人教PEP并用）'
    UNION ALL SELECT '英语', 6, '外研版（三年级起点）', '37', '山东主流（与人教PEP并用）'
    UNION ALL SELECT '英语', 7, '外研版', '37', '山东初中主流'
    UNION ALL SELECT '英语', 8, '外研版', '37', '山东初中主流'
    UNION ALL SELECT '英语', 9, '外研版', '37', '山东初中主流'
) v
LEFT JOIN textbook_versions t
    ON t.subject = v.subject
   AND t.grade = v.grade
   AND t.region = v.region
   AND t.name = v.name
WHERE t.id IS NULL;
