-- 线上后台"页面空数据"诊断 SQL（只读）
-- 用法：mysql -u<user> -p schoolexam < tools/diagnose_admin_empty.sql
-- 用途：一次性查看所有后台页面依赖表的数据量

SELECT '=== 用户与基础 ===' AS section;
SELECT 'users' AS tbl, COUNT(*) AS rows FROM users
UNION ALL SELECT 'admin_users', COUNT(*) FROM admin_users
UNION ALL SELECT 'vip_users', COUNT(*) FROM vip_users;

SELECT '=== 教材版本（S6） ===' AS section;
SELECT 'textbook_versions' AS tbl, COUNT(*) AS rows FROM textbook_versions;

SELECT '=== 充值订单（S4） ===' AS section;
SELECT 'commerce_products' AS tbl, COUNT(*) AS rows FROM commerce_products
UNION ALL SELECT 'commerce_orders', COUNT(*) FROM commerce_orders
UNION ALL SELECT 'commerce_payments', COUNT(*) FROM commerce_payments
UNION ALL SELECT 'commerce_refunds', COUNT(*) FROM commerce_refunds;

SELECT '=== RBAC 权限（S1） ===' AS section;
SELECT 'roles' AS tbl, COUNT(*) AS rows FROM roles
UNION ALL SELECT 'permissions', COUNT(*) FROM permissions
UNION ALL SELECT 'role_permissions', COUNT(*) FROM role_permissions
UNION ALL SELECT 'admin_roles', COUNT(*) FROM admin_roles;

SELECT '=== 审计日志（S1） ===' AS section;
SELECT 'audit_logs' AS tbl, COUNT(*) AS rows FROM audit_logs;

SELECT '=== 知识点标注（S2） ===' AS section;
SELECT 'knowledge_points' AS tbl, COUNT(*) AS rows FROM knowledge_points
UNION ALL SELECT 'kp_annotations', COUNT(*) FROM kp_annotations;

SELECT '=== 掌握度（S3） ===' AS section;
SELECT 'user_kp_mastery' AS tbl, COUNT(*) AS rows FROM user_kp_mastery;

SELECT '=== 任务/激励（S0） ===' AS section;
SELECT 'daily_tasks' AS tbl, COUNT(*) AS rows FROM daily_tasks
UNION ALL SELECT 'tasks', COUNT(*) FROM tasks
UNION ALL SELECT 'task_progress', COUNT(*) FROM task_progress
UNION ALL SELECT 'diamonds', COUNT(*) FROM diamond_accounts;

SELECT '=== 字段存在性检查 ===' AS section;
SELECT 'textbook_versions.region' AS col,
       (SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='textbook_versions' AND COLUMN_NAME='region') AS exists_col
UNION ALL
SELECT 'commerce_orders.status',
       (SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='commerce_orders' AND COLUMN_NAME='status');

SELECT '=== migration 已执行的版本 ===' AS section;
SELECT version_num FROM alembic_version;