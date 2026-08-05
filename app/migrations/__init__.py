"""数据库迁移脚本机制

所有数据库结构调整（建表/加列/种子数据）必须写成版本化迁移脚本，
放在 versions/ 目录下，文件命名：NNN_描述.py，每个脚本提供 upgrade(db)。

执行方式：应用启动时由 runner.run_migrations() 自动执行未应用过的脚本，
已执行版本记录在 schema_migrations 表中（幂等，重复执行安全）。
"""
