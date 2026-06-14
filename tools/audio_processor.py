"""
本地语音转文字（STT）模块。
使用 OpenAI Whisper（small 模型）+ ffmpeg。
- 首次运行会自动下载模型（约 244 MB，缓存在 ~/.cache/whisper/）
- 依赖 ffmpeg，未安装时会给出明确错误指引
"""

import os
import tempfile
import shutil
import streamlit as st

# 全局模型缓存：避免每次调用都重新加载
_MODEL_CACHE = {}


def _check_ffmpeg() -> tuple[bool, str]:
    """检测 ffmpeg 是否可用。返回 (是否可用, 错误信息)。"""
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return True, ""
    return False, (
        "❌ 未检测到 ffmpeg。\n\n"
        "Whisper 依赖 ffmpeg 来处理音频，请按系统安装：\n\n"
        "**Windows (PowerShell 管理员)**：\n"
        "```\nwinget install ffmpeg\n```\n"
        "或从 https://www.gyan.dev/ffmpeg/builds/ 下载后将 `bin/` 加到 PATH。\n\n"
        "**macOS**：\n"
        "```\nbrew install ffmpeg\n```\n\n"
        "**Linux (Ubuntu/Debian)**：\n"
        "```\nsudo apt update && sudo apt install ffmpeg\n```\n\n"
        "安装完成后**重启终端**（让 PATH 生效），再重启 Streamlit。"
    )


@st.cache_resource
def _load_whisper_model(model_size: str = "small"):
    """
    加载 Whisper 模型（Streamlit 缓存层 + 全局字典双保险）。
    首次调用会下载模型，后续调用直接复用。
    """
    if model_size in _MODEL_CACHE:
        return _MODEL_CACHE[model_size]

    import whisper  # 延迟导入，避免未安装时报错
    model = whisper.load_model(model_size)
    _MODEL_CACHE[model_size] = model
    return model


def transcribe_audio(audio_bytes: bytes, suffix: str = ".wav", model_size: str = "small", language: str = "zh") -> str | None:
    """
    将音频字节流转写为文字。

    Args:
        audio_bytes: 音频文件二进制内容（来自 streamlit-mic-recorder）
        suffix: 文件后缀（".wav" / ".mp3" / ".webm" 等）
        model_size: Whisper 模型大小，tiny/base/small/medium/large
        language: 强制语言，"zh" 中文 / "en" 英文 / None 自动检测

    Returns:
        识别出的文字，失败返回 None（错误信息已通过 st.error 展示）。
    """
    # 1) 检查 ffmpeg
    ok, err_msg = _check_ffmpeg()
    if not ok:
        st.error(err_msg)
        return None

    # 2) 写入临时文件（Whisper 需要文件路径）
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # 3) 加载模型
        with st.spinner(f"🔄 加载 Whisper {model_size} 模型（首次需下载 ~244MB）..."):
            model = _load_whisper_model(model_size)

        # 4) 推理
        with st.spinner("🎙️ 正在识别语音..."):
            options = {"language": language, "fp16": False}  # CPU 必须 fp16=False
            result = model.transcribe(tmp_path, **options)
            text = result.get("text", "").strip()
        return text

    except Exception as e:
        st.error(f"❌ 语音识别失败: {e}")
        return None
    finally:
        # 5) 清理临时文件
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
