"""内容 / Blog 域路由包。

main.py 挂载方式（与其它域一致）：
    app.include_router(blog_articles.router,   prefix="/api/blog",      dependencies=user_auth_deps)
    app.include_router(blog_taxonomy.router,   prefix="/api/blog",      dependencies=user_auth_deps)
    app.include_router(blog_workspace.router,  prefix="/api/workspace", dependencies=user_auth_deps)
"""
