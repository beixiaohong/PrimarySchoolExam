"""启动入口"""
import uvicorn

from app.logging_setup import build_log_config

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        # 让 uvicorn 自身的访问/错误日志也按天+大小滚动落盘到 log/
        log_config=build_log_config(),
    )
