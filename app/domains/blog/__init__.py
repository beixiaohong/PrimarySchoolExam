"""D10 内容 / Blog 域（blog）

职责：文章、分类、标签的读写与检索；为工作台提供「最新内容」轻量聚合；
以及工作台模块使用记录（我的应用 / 最近使用）。

为什么是 blog 而不是 content（重要）：
本域成立前，`app/domains/content` 已被「学习内容」域占用（courses / grammar / knowledge /
novel / phrases / reading / textbook / words）。按 blog.md §5「实际实现必须遵循现有项目的
命名规范」与 §27.1「不要为了符合示意图而强制迁移/重命名」，代码、路由、表名统一用 blog
（`/api/blog`、`db_blog_*`），平台导航中文名才用「内容」。

边界纪律（与其余九域一致）：
- 数据归属：db_blog_articles / db_blog_categories / db_blog_tags / db_blog_article_tags
  / db_workspace_app_usage（登记于 docs/data-ownership.md）
- 作者只引用 users.user_id（逻辑外键），不复制用户信息、不新建用户表（blog.md §13.1）
- 鉴权复用 require_user / require_self / _require_admin，不建第二套权限体系
- 其它域只能经本域 contracts.py 访问，禁止跨域 import 模型/服务
- models/schemas 暂留 app/models、app/schemas 共享内核，与其它域一致
"""
