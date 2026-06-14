"""
数学解题 Agent（多模态对话版）。
支持文本输入 / 语音录入 + 多张图片上传 + 多轮对话。
- 有图时走 OpenAI 兼容端点（image_url 多模态）
- 无图时走 chatcompletion_v2（纯文本）
强制思维链 + LaTeX 输出，st.markdown + st.latex 双重渲染。
"""

import re
import base64
import streamlit as st
from core.model import chat, multimodal_chat
from prompts.math import PROMPTS_DICT, EXAMPLE_USER, EXAMPLE_ASSISTANT
from tools.audio_processor import transcribe_audio

# 图片格式 → MIME
_EXT_TO_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


def _file_to_data_url(file) -> str:
    """将 Streamlit UploadedFile 转为 base64 data URL。"""
    ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else "jpeg"
    mime = _EXT_TO_MIME.get(ext, "image/jpeg")
    b64 = base64.b64encode(file.getvalue()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def solve_math_problem(
    history: list[dict],
    question: str,
    image_data_urls: list[str] = None,
) -> str:
    """
    多轮对话解数学题。
    - history: 之前的对话 [{"role": "user/assistant", "content": "..."}]
    - question: 当前用户输入
    - image_data_urls: 当前轮附带的图片（可选）
    返回完整回答（含 LaTeX）。
    """
    system_prompt = PROMPTS_DICT["system_prompt"]

    # ---- 构建 messages ----
    # Few-shot 示例（只在第一轮加入，节省 token）
    few_shot = [
        {"role": "user", "content": EXAMPLE_USER},
        {"role": "assistant", "content": EXAMPLE_ASSISTANT},
    ]

    # 历史对话（跳过 images 字段，只保留 content）
    history_messages = []
    for msg in history:
        history_messages.append({"role": msg["role"], "content": msg["content"]})

    # 当前轮用户消息
    if image_data_urls:
        content_blocks = [{"type": "image_url", "image_url": {"url": url}} for url in image_data_urls]
        content_blocks.append({"type": "text", "text": question})
        current_msg = {"role": "user", "content": content_blocks}
    else:
        current_msg = {"role": "user", "content": question}

    # 组合：system + few-shot + history + current
    messages = few_shot + history_messages + [current_msg]

    # ---- 调用 API ----
    if image_data_urls:
        gen = multimodal_chat(messages=messages, system_prompt=system_prompt)
    else:
        gen = chat(messages=messages, system_prompt=system_prompt)

    full_text = ""
    for chunk in gen:
        full_text += chunk
    return full_text.strip()


def render_with_latex(text: str):
    """
    渲染回答：去除 <think> 标签 → $$...$$ 用 st.latex → 其余用 st.markdown。
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    block_pattern = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
    last_end = 0
    for m in block_pattern.finditer(text):
        before = text[last_end:m.start()]
        if before.strip():
            st.markdown(before)
        st.latex(m.group(1).strip())
        last_end = m.end()
    rest = text[last_end:]
    if rest.strip():
        st.markdown(rest)


def render():
    st.title("🧮 数学解题")
    st.caption("支持文本 / 语音 + 多张图片 · 多轮对话 · LaTeX 公式渲染")

    # ---- 会话状态 ----
    defaults = {
        "math_history": [],       # [{"role": ..., "content": ..., "images": [...]}]
        "math_question_input": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # ========================
    # 侧边栏：图片上传 + 语音
    # ========================
    with st.sidebar:
        st.subheader("📷 图片上传（可选）")
        uploaded_files = st.file_uploader(
            "上传题目截图、手写算式、几何图形等",
            type=["jpg", "jpeg", "png", "gif", "webp"],
            accept_multiple_files=True,
            key="math_image_upload",
            help="支持多张，每张 ≤10MB。本次发送时附带。",
        )
        if uploaded_files:
            for f in uploaded_files:
                size_kb = len(f.getvalue()) / 1024
                st.caption(f"📎 {f.name} ({size_kb:.0f} KB)")

        st.divider()
        st.subheader("🎙️ 语音输入（可选）")
        try:
            from streamlit_mic_recorder import mic_recorder
            audio_data = mic_recorder(
                start_prompt="🎙️ 开始录音",
                stop_prompt="⏹️ 停止录音",
                just_once=False,
                use_container_width=True,
                format="wav",
            )
        except ImportError:
            st.warning("未安装 streamlit-mic-recorder")
            audio_data = None

        if audio_data and audio_data.get("bytes"):
            st.audio(audio_data["bytes"], format="audio/wav")
            if st.button("🔄 识别语音", use_container_width=True):
                text = transcribe_audio(audio_data["bytes"], suffix=".wav")
                if text:
                    st.session_state.math_question_input = text
                    st.success(f"✅ {text}")

        st.divider()
        if st.button("🗑️ 清空对话", use_container_width=True):
            st.session_state.math_history = []
            st.session_state.math_question_input = ""
            st.rerun()

    # ========================
    # 对话历史展示
    # ========================
    if not st.session_state.math_history:
        st.info("💬 在下方输入数学问题开始对话（可选上传图片、语音输入）")

    for msg in st.session_state.math_history:
        with st.chat_message(msg["role"]):
            if msg.get("images"):
                st.caption(f"📷 已上传 {len(msg['images'])} 张图片：{', '.join(msg['images'])}")
            if msg["role"] == "user":
                st.markdown(msg["content"])
            else:
                render_with_latex(msg["content"])

    # ========================
    # 底部聊天输入框
    # ========================
    # 如果语音识别了文字，预填到输入框
    default_input = st.session_state.math_question_input or ""

    if user_input := st.chat_input(
        "输入数学问题...（可选：先在左侧上传图片）",
        key="math_chat_input",
    ):
        # 清空语音预填
        st.session_state.math_question_input = ""

        # 转换图片
        image_urls = []
        image_names = []
        if uploaded_files:
            for f in uploaded_files:
                if len(f.getvalue()) > 10 * 1024 * 1024:
                    st.error(f"❌ {f.name} 超过 10MB，已跳过")
                    continue
                image_urls.append(_file_to_data_url(f))
                image_names.append(f.name)

        # 只有图片没有文字时，自动加提示
        display_text = user_input
        if not user_input.strip() and image_urls:
            user_input = "请分析这张图片中的数学问题，并给出详细的解题步骤。"
            display_text = "📷 [看图解题]"

        # 保存用户消息
        user_msg = {"role": "user", "content": display_text}
        if image_names:
            user_msg["images"] = image_names
        st.session_state.math_history.append(user_msg)

        # 显示用户消息
        with st.chat_message("user"):
            if image_names:
                st.caption(f"📷 已上传 {len(image_names)} 张图片：{', '.join(image_names)}")
            st.markdown(display_text)

        # AI 回答
        with st.chat_message("assistant"):
            with st.spinner("🤔 AI 正在推理中..."):
                try:
                    answer = solve_math_problem(
                        history=st.session_state.math_history[:-1],  # 不含当前轮
                        question=user_input,
                        image_data_urls=image_urls if image_urls else None,
                    )
                    render_with_latex(answer)
                    st.session_state.math_history.append({"role": "assistant", "content": answer})
                except Exception as e:
                    st.error(f"❌ 解题失败: {e}")

    # ---- 语音识别结果预填提示 ----
    if st.session_state.math_question_input:
        st.caption(f"🎤 语音识别结果：「{st.session_state.math_question_input}」— 直接在上方输入框回车发送，或修改后发送")
