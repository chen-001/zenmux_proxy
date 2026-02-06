"""
代理配置
"""
import os

# HTTP 代理配置
HTTP_PROXY = "http://127.0.0.1:10808"
HTTPS_PROXY = "http://127.0.0.1:10808"

# Moonshot API 配置
MOONSHOT_API_KEY = os.getenv("ZENMUX_API_KEY", "")
MOONSHOT_BASE_URL = os.getenv("MOONSHOT_BASE_URL", "https://zenmux.ai/api/anthropic")

# 代理服务配置
PROXY_HOST = os.getenv("PROXY_HOST", "0.0.0.0")
PROXY_PORT = int(os.getenv("PROXY_PORT", "8000"))

# 调试模式
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# 自动修复配置
AUTO_FIX_MISSING_REASONING = True
AUTO_ENABLE_STREAM_FOR_THINKING = True
MIN_TOKENS_FOR_THINKING = 16000