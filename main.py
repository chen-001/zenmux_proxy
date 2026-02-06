"""
Kimi Thinking 模型代理服务
修复 reasoning_content 缺失导致的 400 错误
"""
import json
import httpx
import asyncio
from uuid import uuid4
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from contextlib import asynccontextmanager
from message_transformer import ReasoningContentTransformer
from anthropic_adapter import AnthropicAdapter
from config import HTTPS_PROXY

# 配置
MOONSHOT_BASE_URL = "https://zenmux.ai/api/anthropic"
DEFAULT_TIMEOUT = 120.0

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    transport = httpx.AsyncHTTPTransport(proxy=HTTPS_PROXY)
    app.state.client = httpx.AsyncClient(
        base_url=MOONSHOT_BASE_URL,
        timeout=httpx.Timeout(DEFAULT_TIMEOUT, connect=10.0),
        http2=True,
        transport=transport
    )
    yield
    await app.state.client.aclose()

app = FastAPI(title="Kimi Thinking Proxy", version="1.0.0", lifespan=lifespan)

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    代理 chat completions 接口，修复 reasoning_content 问题
    """
    try:
        body = await request.json()
        
        # ===== 关键修复 1: 修复请求消息 =====
        if "messages" in body:
            original_messages = body["messages"]
            body["messages"] = ReasoningContentTransformer.fix_messages(original_messages)
            
            # 打印调试信息（生产环境可移除）
            print(f"[Proxy] Fixed {len(original_messages)} messages")
        
        # ===== 关键修复 2: 确保启用了 thinking 时，max_tokens 足够大 =====
        if body.get("thinking") or body.get("extra_body", {}).get("thinking"):
            if body.get("max_tokens", 0) < 16000:
                body["max_tokens"] = 16000
            # 确保 temperature 为 1.0（Kimi K2.5 Thinking 要求）
            body["temperature"] = 1.0
        
        # ===== 关键修复 3: 确保使用流式传输（避免超时） =====
        is_streaming = body.get("stream", False)
        if not is_streaming and body.get("thinking"):
            # 对于 thinking 模式，强制使用流式以避免大响应超时
            print("[Proxy] Auto-enabling stream for thinking mode")
            body["stream"] = True
            is_streaming = True
        
        # 转发请求到 Moonshot API
        headers = {
            "Authorization": request.headers.get("authorization", ""),
            "Content-Type": "application/json",
        }
        
        if is_streaming:
            return await handle_streaming_response(request, body, headers)
        else:
            return await handle_non_streaming_response(request, body, headers)
            
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def handle_non_streaming_response(request: Request, body: dict, headers: dict):
    """处理非流式响应"""
    response = await request.app.state.client.post(
        "/chat/completions",
        json=body,
        headers=headers
    )
    
    if response.status_code != 200:
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers)
        )
    
    data = response.json()
    
    # ===== 关键修复 4: 修复响应中的 assistant 消息 =====
    if "choices" in data:
        for choice in data["choices"]:
            if "message" in choice:
                choice["message"] = ReasoningContentTransformer.ensure_assistant_message_complete(
                    choice["message"]
                )
    
    return JSONResponse(content=data)

async def handle_streaming_response(request: Request, body: dict, headers: dict):
    """处理流式响应，实时修复每个 chunk"""
    
    async def generate():
        async with request.app.state.client.stream(
            "POST",
            "/chat/completions",
            json=body,
            headers=headers
        ) as response:
            
            if response.status_code != 200:
                error_content = await response.aread()
                yield f"data: {json.dumps({'error': error_content.decode()})}\n\n"
                return
            
            async for line in response.aiter_lines():
                if not line:
                    continue
                
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    
                    if data_str == "[DONE]":
                        yield "data: [DONE]\n\n"
                        continue
                    
                    try:
                        chunk = json.loads(data_str)
                        
                        # ===== 关键修复 5: 修复每个流式 chunk =====
                        if "choices" in chunk:
                            for choice in chunk["choices"]:
                                if "delta" in choice:
                                    delta = choice["delta"]
                                    
                                    # 处理 reasoning_content 字段
                                    if delta.get("role") == "assistant":
                                        if "reasoning_content" not in delta:
                                            # 如果 content 以 <thinking> 开头，提取它
                                            content = delta.get("content", "")
                                            if content and content.startswith("<thinking>"):
                                                end_idx = content.find("</thinking>")
                                                if end_idx != -1:
                                                    delta["reasoning_content"] = content[10:end_idx]
                                                    delta["content"] = content[end_idx+11:]
                                                else:
                                                    delta["reasoning_content"] = content[10:]
                                                    delta["content"] = ""
                                            else:
                                                delta["reasoning_content"] = None
                        
                        yield f"data: {json.dumps(chunk)}\n\n"
                        
                    except json.JSONDecodeError:
                        yield f"{line}\n\n"
                else:
                    yield f"{line}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@app.get("/v1/models")
async def list_models(request: Request):
    """代理模型列表接口"""
    headers = {"Authorization": request.headers.get("authorization", "")}
    response = await request.app.state.client.get("/models", headers=headers)
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers={"Content-Type": "application/json"}
    )

@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "service": "kimi-thinking-proxy"}


@app.post("/v1/messages")
async def anthropic_messages(request: Request):
    """
    Anthropic API 格式的代理接口
    直接转发到上游 Anthropic API，修复 reasoning_content 问题
    """
    try:
        body = await request.json()

        # 修复消息历史中的 reasoning_content 问题
        if "messages" in body:
            body["messages"] = ReasoningContentTransformer.fix_anthropic_messages(
                body["messages"]
            )

        # Anthropic 使用 x-api-key 头进行认证
        auth_header = request.headers.get("x-api-key", "")
        if not auth_header:
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                auth_header = auth[7:]
        headers = {
            "x-api-key": auth_header,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        is_streaming = body.get("stream", False)

        if is_streaming:
            return await handle_anthropic_streaming(request, body, headers)
        else:
            return await handle_anthropic_non_streaming(request, body, headers)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def handle_anthropic_non_streaming(request: Request, body: dict, headers: dict):
    """直接转发 Anthropic 非流式请求和响应"""
    print(f"[Debug] Request headers: {headers}")
    print(f"[Debug] Request body: {json.dumps(body, ensure_ascii=False)[:500]}")

    response = await request.app.state.client.post(
        "/v1/messages",
        json=body,
        headers=headers
    )

    print(f"[Debug] Response status: {response.status_code}")
    print(f"[Debug] Response content: {response.text[:1000]}")

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=dict(response.headers)
    )


async def handle_anthropic_streaming(request: Request, body: dict, headers: dict):
    """直接转发 Anthropic 流式请求和响应"""

    async def generate():
        async with request.app.state.client.stream(
            "POST",
            "/v1/messages",
            json=body,
            headers=headers,
            timeout=120.0
        ) as response:
            print(f"[Debug] Stream response status: {response.status_code}")

            if response.status_code != 200:
                error_content = await response.aread()
                print(f"[Debug] Stream error: {error_content.decode()[:500]}")
                yield error_content
                return

            async for chunk in response.aiter_text():
                yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)