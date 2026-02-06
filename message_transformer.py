"""
处理 reasoning_content 字段的转换和修复
"""
import json
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

class ReasoningContentTransformer:
    """
    修复 Kimi Thinking 模型在工具调用时的 reasoning_content 缺失问题
    """
    
    @staticmethod
    def fix_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        修复请求中的消息历史，确保 assistant 消息包含 reasoning_content
        """
        fixed_messages = []
        
        for msg in messages:
            if msg.get("role") == "assistant":
                # 检查是否缺少 reasoning_content 但包含工具调用
                has_tool_calls = "tool_calls" in msg and msg["tool_calls"]
                has_reasoning = "reasoning_content" in msg
                
                if has_tool_calls and not has_reasoning:
                    # 情况1：如果 content 包含 <thinking> 标签，提取出来
                    content = msg.get("content", "") or ""
                    reasoning_match = re.search(r'<thinking>(.*?)</thinking>', content, re.DOTALL)
                    
                    if reasoning_match:
                        msg["reasoning_content"] = reasoning_match.group(1).strip()
                        msg["content"] = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL).strip()
                    else:
                        # 情况2：构造一个占位 reasoning_content（告诉模型"继续思考"）
                        # 这是关键：让 Kimi API 知道这是一个延续的思考过程
                        msg["reasoning_content"] = "[Continuing previous tool execution analysis...]"
                
                # 确保 reasoning_content 不为 None，而是字符串
                if "reasoning_content" in msg and msg["reasoning_content"] is None:
                    msg["reasoning_content"] = ""
                    
            fixed_messages.append(msg)
        
        return fixed_messages
    
    @staticmethod
    def add_reasoning_to_assistant_chunk(chunk: Dict[str, Any]) -> Dict[str, Any]:
        """
        为流式响应中的 assistant 消息块添加 reasoning_content 字段
        """
        if "choices" in chunk and len(chunk["choices"]) > 0:
            choice = chunk["choices"][0]
            if "delta" in choice:
                delta = choice["delta"]
                
                # 如果 delta 包含 content 或 tool_calls，但没有 reasoning_content
                if ("content" in delta or "tool_calls" in delta) and "reasoning_content" not in delta:
                    # 检查是否是 assistant 角色
                    role = delta.get("role", "")
                    if role == "assistant" or ("content" in delta and delta.get("content")):
                        delta["reasoning_content"] = None  # 或 "" 或实际的推理内容
        
        return chunk

    @staticmethod
    def ensure_assistant_message_complete(message: Dict[str, Any]) -> Dict[str, Any]:
        """
        确保非流式响应中的 assistant 消息包含 reasoning_content
        """
        if message.get("role") == "assistant":
            if "reasoning_content" not in message:
                # 尝试从 content 中提取 <thinking> 标签
                content = message.get("content", "") or ""
                if "<thinking>" in content:
                    match = re.search(r'<thinking>(.*?)</thinking>', content, re.DOTALL)
                    if match:
                        message["reasoning_content"] = match.group(1).strip()
                        message["content"] = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL).strip()
                else:
                    message["reasoning_content"] = None

        return message

    @staticmethod
    def fix_anthropic_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        修复 Anthropic 格式的消息历史，确保 assistant 消息包含 reasoning_content
        """
        fixed_messages = []

        for msg in messages:
            if msg.get("role") == "assistant":
                # 检查是否有 thinking 字段（Anthropic 格式）
                content = msg.get("content", [])

                # content 是数组格式
                if isinstance(content, list):
                    has_thinking = any(c.get("type") == "thinking" for c in content)
                    has_tool_use = any(c.get("type") == "tool_use" for c in content)

                    # 如果有 tool_use 但没有 thinking，添加一个占位 thinking
                    if has_tool_use and not has_thinking:
                        # 在数组开头添加占位 thinking
                        content.insert(0, {
                            "type": "thinking",
                            "thinking": "[Continuing previous tool execution analysis...]"
                        })
                        msg["content"] = content

            fixed_messages.append(msg)

        return fixed_messages