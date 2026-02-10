# Kimi Thinking Proxy

Kimi Thinking 模型代理服务，用于修复 `reasoning_content` 缺失导致的 400 错误。

将 Anthropic API 格式转换为 OpenAI API 格式，并处理 Kimi K2.5 Thinking 模型的特殊逻辑。

## 功能特性

- ✅ 修复 reasoning_content 缺失问题
- ✅ 支持 Anthropic API 格式 (`/v1/messages`)
- ✅ 支持 OpenAI API 格式 (`/v1/chat/completions`)
- ✅ 支持流式和非流式响应
- ✅ 自动处理 thinking 模式参数

## 安装依赖

```bash
pip install fastapi uvicorn httpx
```

或使用 requirements.txt：

```bash
pip install -r requirements.txt
```

## 环境变量配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `ZENMUX_API_KEY` | API 密钥 | 空字符串 |
| `MOONSHOT_BASE_URL` | API 基础地址 | `https://zenmux.ai/api/anthropic` |
| `PROXY_HOST` | 服务监听地址 | `0.0.0.0` |
| `PROXY_PORT` | 服务监听端口 | `8000` |
| `DEBUG` | 调试模式 | `false` |

### 配置示例

```bash
export ZENMUX_API_KEY="your-api-key-here"
export PROXY_PORT="8080"
export DEBUG="true"
```

## 运行方式

### 1. 开发模式（直接使用 uvicorn）

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 生产模式（使用 Gunicorn + Uvicorn Workers）

推荐使用 Gunicorn 作为进程管理器，配合 Uvicorn worker 运行：

```bash
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

参数说明：
- `-w 4`：启动 4 个工作进程（可根据 CPU 核心数调整）
- `-k uvicorn.workers.UvicornWorker`：使用 Uvicorn worker 类
- `--bind 0.0.0.0:8000`：绑定地址和端口

#### 其他常用参数

```bash
# 后台运行 + 日志输出
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --daemon \
    --access-logfile access.log \
    --error-logfile error.log

# 使用配置文件
gunicorn main:app -c gunicorn.conf.py
```

#### Gunicorn 配置文件示例（gunicorn.conf.py）

```python
import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"
keepalive = 5
errorlog = "-"
accesslog = "-"
```

## API 使用

### Anthropic 格式

```bash
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: your-api-key" \
  -d '{
    "model": "kimi-k2.5",
    "max_tokens": 16000,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### OpenAI 格式

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-api-key" \
  -d '{
    "model": "kimi-k2.5",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### 健康检查

```bash
curl http://localhost:8000/health
```

## 系统架构

```
Client (Claude Desktop/Claude Code)
    ↓
Kimi Thinking Proxy (本项目)
    ↓
zenmux.ai (Anthropic API 格式)
```

## 代理配置

如需通过代理访问上游 API，修改 `config.py` 中的代理设置：

```python
HTTP_PROXY = "http://127.0.0.1:10808"
HTTPS_PROXY = "http://127.0.0.1:10808"
```

## 许可证

MIT
