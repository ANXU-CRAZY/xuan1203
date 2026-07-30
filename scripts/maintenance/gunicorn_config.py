# Gunicorn 配置文件
# 使用方法: gunicorn -c gunicorn_config.py config.wsgi:application

import multiprocessing
import os

# 服务器绑定
bind = "unix:/run/gunicorn.sock"  # 使用 Unix socket 与 Nginx 通信
# bind = "127.0.0.1:8000"  # 或使用 TCP socket

# Worker 进程数
# 公式: workers = 2 * CPU核心数 + 1
# 对于 2 核服务器: 2*2+1 = 5
# 对于 4 核服务器: 2*4+1 = 9
workers = multiprocessing.cpu_count() * 2 + 1

# Worker 类型 - gthread 支持多线程，提高并发能力
worker_class = "gthread"

# 每个 worker 的线程数
threads = 2

# Worker 超时时间（秒）
timeout = 60

# 优雅关闭超时
graceful_timeout = 30

# Worker 自动重启
# 每个 worker 处理 500 个请求后自动重启，释放内存
# 这对于 DEBUG=True 遗留问题特别重要
max_requests = 500
max_requests_jitter = 50  # 随机抖动，避免所有 worker 同时重启

# 日志
accesslog = "-"  # 输出到 stdout
errorlog = "-"   # 输出到 stderr
loglevel = "info"

# 进程命名
proc_name = "yellow_river_gunicorn"

# 预加载应用（可选，加快启动速度，但调试时建议关闭）
# preload_app = True

# Keepalive 连接
keepalive = 5

# 环境变量
raw_env = [
    "DJANGO_SETTINGS_MODULE=config.settings",
]
