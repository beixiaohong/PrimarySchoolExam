"""启动入口"""
import uvicorn

from app.logging_setup import build_log_config

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        # 只监听 app/ 源码目录，避免 log/、output/、temp/、data/ 等运行时写入目录
        # 触发无限 "change detected" 循环（日志每写一条就触发一次文件变更检测）
        reload_dirs=["app"],
        reload_excludes=["log/*", "output/*", "temp/*", "data/*", "*.log", "*.db"],
        # 让 uvicorn 自身的访问/错误日志也按天+大小滚动落盘到 log/
        log_config=build_log_config(),
    )
