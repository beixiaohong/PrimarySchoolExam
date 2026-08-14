# 迁移脚本说明（app/migrations/versions/）

本目录共 **42** 个版本化迁移脚本，由 `app/migrations/runner.py` 在启动时按编号顺序执行。

## 两类脚本

- **001 – 025（历史基线，MySQL 下不执行）**
  这些是早期 SQLite 方言迁移（建表 / 重建表 / 种子数据）。项目统一为 MySQL 后，
  表结构改由 `Base.metadata.create_all`（`app/database.init_db`）统一建立，因此 runner
  在 MySQL 侧**仅将这些版本预置为「已执行」**，不再运行其 SQLite 方言 SQL。
  → 它们是"占位基线"，**请勿期待在 MySQL 上产生任何表结构变更**；修改它们不会生效。

- **026 – 042（生效的幂等迁移，MySQL 真实执行）**
  全部为幂等实现（inspector / checkfirst / try-except），启动时会按编号顺序真实执行，
  用于加列、建表、种子数据等。新增迁移请从 043 起递增编号。

## 新增迁移规范
1. 文件名：`0NN_简短说明.py`（NN 用足三位，如 `043_add_xxx.py`）。
2. 必须幂等：用 `runner` 提供的 `_ensure_column` 或 `inspector` 判断已存在则跳过。
3. 不要改 001–025（它们不被执行）；新增需求一律从 026+ 之后编号。

> 排查"为什么我的迁移没跑"：先看 `schema_migrations` 表是否已有该版本；
> 001–025 必然已存在（基线预置），026+ 才会真正执行。
