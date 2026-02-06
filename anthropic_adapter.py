"""
Anthropic API 格式与 OpenAI API 格式之间的适配器
"""
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4


class AnthropicAdapter:
    """Anthropic <-> OpenAI 格式转换器"""

    @staticmethod
    def anthropic_to_openai_messages(anthropic_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将 Anthropic 消息格式转换为 OpenAI 格式"""
        openai_messages = []
        for msg in anthropic_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Anthropic 支持 content 为数组格式，需要转换为字符串
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                content = "\n".join(text_parts)

            openai_messages.append({"role": role, "content": content})
        return openai_messages

    @staticmethod
    def openai_to_anthropic_response(openai_response: Dict[str, Any], model: str) -> Dict[str, Any]:
        """将 OpenAI 响应格式转换为 Anthropic 响应格式"""
        anthropic_response = {
            "id": f"msg_{uuid4().hex[:24]}",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0}
        }

        # 提取 usage
        if "usage" in openai_response:
            usage = openai_response["usage"]
            anthropic_response["usage"] = {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0)
            }

        # 提取内容
        if "choices" in openai_response and len(openai_response["choices"]) > 0:
            choice = openai_response["choices"][0]
            message = choice.get("message", {})
            content = message.get("content", "")

            # 处理 reasoning_content
            reasoning = message.get("reasoning_content")
            if reasoning:
                anthropic_response["content"].append({
                    "type": "thinking",
                    "thinking": reasoning
                })

            if content:
                anthropic_response["content"].append({
                    "type": "text",
                    "text": content
                })

            # 处理 stop_reason
            finish_reason = choice.get("finish_reason")
            if finish_reason == "stop":
                anthropic_response["stop_reason"] = "end_turn"
            elif finish_reason == "length":
                anthropic_response["stop_reason"] = "max_tokens"

        return anthropic_response

    @staticmethod
    def anthropic_request_to_openai(anthropic_body: Dict[str, Any]) -> Dict[str, Any]:
        """将 Anthropic 请求转换为 OpenAI 请求"""
        openai_body = {
            "model": anthropic_body.get("model", "kimi-k2.5"),
            "messages": AnthropicAdapter.anthropic_to_openai_messages(
                anthropic_body.get("messages", [])
            ),
            "max_tokens": anthropic_body.get("max_tokens", 4096),
        }

        # 可选参数
        if "temperature" in anthropic_body:
            openai_body["temperature"] = anthropic_body["temperature"]
        if "top_p" in anthropic_body:
            openai_body["top_p"] = anthropic_body["top_p"]
        if "stop_sequences" in anthropic_body:
            openai_body["stop"] = anthropic_body["stop_sequences"]
        if "stream" in anthropic_body:
            openai_body["stream"] = anthropic_body["stream"]

        return openai_body

    @staticmethod
    def openai_chunk_to_anthropic(openai_chunk: Dict[str, Any], model: str) -> Optional[Dict[str, Any]]:
        """将 OpenAI 流式 chunk 转换为 Anthropic 流式事件"""
        if "choices" not in openai_chunk or len(openai_chunk["choices"]) == 0:
            return None

        choice = openai_chunk["choices"][0]
        delta = choice.get("delta", {})

        # Anthropic 流式事件格式
        anthropic_event = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {}
        }

        # 处理 content
        content = delta.get("content", "")
        if content:
            anthropic_event["delta"] = {"type": "text_delta", "text": content}
            return anthropic_event

        # 处理 reasoning_content
        reasoning = delta.get("reasoning_content")
        if reasoning:
            anthropic_event["delta"] = {"type": "thinking_delta", "thinking": reasoning}
            return anthropic_event

        # 检查是否完成
        if choice.get("finish_reason"):
            return {"type": "message_stop"}

        return None