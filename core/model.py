"""
MiniMax API 封装，支持流式输出。
- chat():            chatcompletion_v2 端点（纯文本）
- multimodal_chat(): OpenAI 兼容端点（图片/视频+文本，仅 M3）
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# 纯文本端点（MiniMax 原生格式）
ENDPOINT_V2 = "https://api.minimax.chat/v1/text/chatcompletion_v2"
# 多模态端点（OpenAI 兼容格式，支持 image_url/video_url）
ENDPOINT_OPENAI = "https://api.minimaxi.com/v1/chat/completions"


def _build_headers() -> dict:
    api_key = os.getenv("MINIMAX_API_KEY", "")
    if not api_key:
        raise ValueError("环境变量 MINIMAX_API_KEY 未设置，请在 .env 文件中配置")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def chat(messages: list[dict], system_prompt: str = "", model: str = "MiniMax-M3", stream: bool = True, **kwargs):
    """
    调用 MiniMax chatcompletion_v2（纯文本）。

    Args:
        messages: 对话历史 [{"role": "user/assistant", "content": "..."}, ...]
        system_prompt: 系统提示词
        model: 模型名称
        stream: 是否流式输出
        **kwargs: 其他参数 (temperature, max_tokens 等)

    Yields:
        如果是流式：逐 chunk 返回 delta 文本
        如果不是流式：返回完整响应的 dict
    """
    headers = _build_headers()

    payload = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }

    if system_prompt:
        payload["system_prompt"] = system_prompt

    payload.update(kwargs)

    resp = requests.post(ENDPOINT_V2, headers=headers, json=payload, stream=stream, timeout=120)

    if resp.status_code != 200:
        raise RuntimeError(f"API 请求失败 ({resp.status_code}): {resp.text}")

    if stream:
        return _parse_stream(resp)
    else:
        return resp.json()


def multimodal_chat(messages: list[dict], system_prompt: str = "", model: str = "MiniMax-M3", stream: bool = True, **kwargs):
    """
    调用 OpenAI 兼容端点（支持图片/视频输入，仅 M3）。
    messages 中的 content 可以是 list（多模态内容块）：
        [{"type": "text", "text": "..."}, {"type": "image_url", "image_url": {"url": "data:..."}}]
    """
    headers = _build_headers()

    # OpenAI 兼容格式：system prompt 放在 messages 数组里
    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    payload = {
        "model": model,
        "messages": full_messages,
        "stream": stream,
    }
    payload.update(kwargs)

    resp = requests.post(ENDPOINT_OPENAI, headers=headers, json=payload, stream=stream, timeout=180)

    if resp.status_code != 200:
        raise RuntimeError(f"API 请求失败 ({resp.status_code}): {resp.text}")

    if stream:
        return _parse_stream(resp)
    else:
        return resp.json()


def _parse_stream(resp: requests.Response):
    """逐行解析 SSE 流，yield 每个 chunk 的文本增量。"""
    for line in resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
            except json.JSONDecodeError:
                continue
