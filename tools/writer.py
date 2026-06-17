"""
AI 创作助手。
多题材选择 → 参数调节 → 流式生成 → 多轮对话 → AI 朗读。
"""

import os
import requests
import streamlit as st
from core.model import chat
from prompts.writer import WRITER_TEMPLATES, CREATIVE_STYLES, STYLE_LABELS, DEFAULT_STYLE

# 实用文体默认 temperature（严谨输出），创意体裁在侧边栏由用户调节
PRACTICAL_TEMPERATURE = 0.3

# T2A 语音合成
T2A_URL = "https://api.minimaxi.com/v1/t2a_v2"
VOICES = {
    "male-qn-qingse": "青涩青年",
    "male-qn-jingying": "精英青年",
    "female-shaonv": "少女",
    "female-yujie": "御姐",
    "female-tianmei": "甜美女性",
    "female-chengshu": "成熟女性",
    "Chinese (Mandarin)_News_Anchor": "新闻女声",
    "Chinese (Mandarin)_Radio_Host": "电台男主播",
    "Chinese (Mandarin)_Lyrical_Voice": "抒情男声",
    "Chinese (Mandarin)_Gentleman": "温润男声",
}


def synthesize_speech(text: str, voice_id: str = "male-qn-jingying", speed: float = 1.0) -> bytes | None:
    """调用 MiniMax T2A 合成语音。"""
    api_key = os.getenv("MINIMAX_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "speech-2.8-hd",
        "text": text[:5000],  # T2A 限制
        "stream": False,
        "voice_setting": {"voice_id": voice_id, "speed": speed, "vol": 1.0, "pitch": 0, "emotion": "neutral"},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
        "subtitle_enable": False,
    }
    try:
        resp = requests.post(T2A_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code != 200:
            return None
        result = resp.json()
        if result.get("base_resp", {}).get("status_code") != 0:
            return None
        audio_hex = result.get("data", {}).get("audio", "")
        return bytes.fromhex(audio_hex) if audio_hex else None
    except Exception:
        return None


def generate_text(style_key: str, user_input: str, temperature: float, word_count: int = 500) -> str:
    """根据题材和用户输入调用 API 生成文本。"""
    template = WRITER_TEMPLATES[style_key]
    system_prompt = template["system_prompt"]
    user_prompt = template["user_prompt"].format(user_input=user_input)

    # 注入字数控制
    user_prompt += f"\n\n（请将输出控制在约 {word_count} 字以内）"

    messages = [{"role": "user", "content": user_prompt}]
    full_text = ""
    for chunk in chat(messages=messages, system_prompt=system_prompt, temperature=temperature):
        full_text += chunk
    return full_text


def _render_writing():
    """写作模块：多题材创作 + 朗读。"""
    st.caption("选择题材，调节参数，AI 为你撰写高质量内容，支持朗读")

    # ---- 会话状态 ----
    if "writer_messages" not in st.session_state:
        st.session_state.writer_messages = []
    if "writer_style" not in st.session_state:
        st.session_state.writer_style = DEFAULT_STYLE
    if "writer_temperature" not in st.session_state:
        st.session_state.writer_temperature = 0.8

    # ---- 侧边栏：创意体裁专属参数 ----
    is_creative = st.session_state.writer_style in CREATIVE_STYLES

    with st.sidebar:
        st.divider()
        if is_creative:
            st.subheader("创造力设置")
            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=1.0,
                value=st.session_state.writer_temperature,
                step=0.05,
                key="sidebar_temperature",
                help="控制输出的随机性和创造性",
            )
            st.session_state.writer_temperature = temperature

            st.caption(
                "💡 **较高值（0.8–1.0）**：更有创意、出人意料、文学性强\n"
                "💡 **中等值（0.4–0.7）**：创意与稳定兼顾\n"
                "💡 **较低值（0.0–0.3）**：更严谨、保守、可预测"
            )
        else:
            st.caption("当前体裁为实用文体，使用默认严谨模式")

    # ---- 主区域参数 ----
    col1, col2, col3, col4 = st.columns([2, 0.8, 0.7, 0.7])
    with col1:
        style_key = st.selectbox(
            "写作题材",
            STYLE_LABELS,
            key="writer_style",
        )
    with col2:
        # 智能默认字数：诗歌类偏短，其他偏长
        if style_key in ("现代诗", "古诗词"):
            default_words = 200
        elif style_key == "微小说":
            default_words = 400
        else:
            default_words = 500
        word_count = st.number_input(
            "目标字数",
            min_value=50,
            max_value=3000,
            value=default_words,
            step=50,
            key="writer_word_count",
        )
    with col3:
        if is_creative:
            st.metric("创造性", f"{st.session_state.writer_temperature:.2f}")
        else:
            st.metric("创造性", f"{PRACTICAL_TEMPERATURE:.1f}")
    with col4:
        if st.button("清空对话", key="clear_writer"):
            st.session_state.writer_messages = []
            st.rerun()

    # 确定实际使用的 temperature
    effective_temp = st.session_state.writer_temperature if is_creative else PRACTICAL_TEMPERATURE

    # ---- 风格说明 ----
    with st.expander(f"当前题材：{style_key} — 风格说明", expanded=False):
        st.caption(WRITER_TEMPLATES[style_key]["system_prompt"])

    # ---- 对话历史 ----
    for msg in st.session_state.writer_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ---- 输入区 ----
    user_input = st.text_area(
        "写作任务",
        placeholder="描述你想写的内容...",
        height=100,
        key="writer_input",
        label_visibility="collapsed",
    )

    if st.button("开始写作", type="primary", disabled=not user_input.strip(), use_container_width=True):
        display_input = f"**【{style_key}】**\n\n{user_input}"
        st.session_state.writer_messages.append({"role": "user", "content": display_input})

        with st.chat_message("user"):
            st.markdown(display_input)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            with st.spinner("AI 正在创作..."):
                full_response = generate_text(style_key, user_input, effective_temp, word_count)
                placeholder.markdown(full_response)

        st.session_state.writer_messages.append({"role": "assistant", "content": full_response})
        st.rerun()

    # ---- 底部：导出 + 朗读 ----
    if st.session_state.writer_messages:
        st.divider()
        last_text = ""
        for m in reversed(st.session_state.writer_messages):
            if m["role"] == "assistant":
                last_text = m["content"]
                break
        if last_text:
            col_dl, col_voice = st.columns(2)
            with col_dl:
                st.download_button(
                    label="⬇️ 导出为文本",
                    data=last_text,
                    file_name="ai_writing.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            with col_voice:
                with st.expander("🔊 朗读设置", expanded=False):
                    voice_id = st.selectbox("音色", list(VOICES.keys()), format_func=lambda k: VOICES[k], key="writer_voice")
                    speed = st.slider("语速", 0.5, 2.0, 1.0, 0.1, key="writer_voice_speed")
                    if st.button("🔊 朗读最新作品", use_container_width=True):
                        with st.spinner("正在合成语音..."):
                            audio = synthesize_speech(last_text, voice_id=voice_id, speed=speed)
                            if audio:
                                st.session_state.writer_audio = audio
                            else:
                                st.error("语音合成失败")
                        st.rerun()

            # 播放音频
            if st.session_state.get("writer_audio"):
                st.audio(st.session_state.writer_audio, format="audio/mp3")
                st.download_button(
                    label="⬇️ 下载音频",
                    data=st.session_state.writer_audio,
                    file_name="ai_writing_voice.mp3",
                    mime="audio/mp3",
                    use_container_width=True,
                )


# ====================== 主入口 ======================

def render():
    """AI 创作助手：多题材写作 + AI 朗读。"""
    st.title("✍️ AI 创作助手")
    st.caption("选择题材，调节参数，AI 为你撰写高质量内容，支持朗读")

    # ---- 会话状态 ----
    if "writer_messages" not in st.session_state:
        st.session_state.writer_messages = []
    if "writer_style" not in st.session_state:
        st.session_state.writer_style = DEFAULT_STYLE
    if "writer_temperature" not in st.session_state:
        st.session_state.writer_temperature = 0.8

    # ---- 侧边栏：创意体裁专属参数 ----
    is_creative = st.session_state.writer_style in CREATIVE_STYLES

    with st.sidebar:
        st.divider()
        if is_creative:
            st.subheader("创造力设置")
            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=1.0,
                value=st.session_state.writer_temperature,
                step=0.05,
                key="sidebar_temperature",
                help="控制输出的随机性和创造性",
            )
            st.session_state.writer_temperature = temperature

            st.caption(
                "💡 **较高值（0.8–1.0）**：更有创意、出人意料、文学性强\n"
                "💡 **中等值（0.4–0.7）**：创意与稳定兼顾\n"
                "💡 **较低值（0.0–0.3）**：更严谨、保守、可预测"
            )
        else:
            st.caption("当前体裁为实用文体，使用默认严谨模式")

    # ---- 主区域参数 ----
    col1, col2, col3, col4 = st.columns([2, 0.8, 0.7, 0.7])
    with col1:
        style_key = st.selectbox("写作题材", STYLE_LABELS, key="writer_style")
    with col2:
        if style_key in ("现代诗", "古诗词"):
            default_words = 200
        elif style_key == "微小说":
            default_words = 400
        else:
            default_words = 500
        word_count = st.number_input("目标字数", min_value=50, max_value=3000, value=default_words, step=50, key="writer_word_count")
    with col3:
        if is_creative:
            st.metric("创造性", f"{st.session_state.writer_temperature:.2f}")
        else:
            st.metric("创造性", f"{PRACTICAL_TEMPERATURE:.1f}")
    with col4:
        if st.button("清空对话", key="clear_writer"):
            st.session_state.writer_messages = []
            st.rerun()

    effective_temp = st.session_state.writer_temperature if is_creative else PRACTICAL_TEMPERATURE

    with st.expander(f"当前题材：{style_key} — 风格说明", expanded=False):
        st.caption(WRITER_TEMPLATES[style_key]["system_prompt"])

    # ---- 对话历史 ----
    for msg in st.session_state.writer_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ---- 输入区 ----
    user_input = st.text_area(
        "写作任务",
        placeholder="描述你想写的内容...",
        height=100,
        key="writer_input",
        label_visibility="collapsed",
    )

    if st.button("开始写作", type="primary", disabled=not user_input.strip(), use_container_width=True):
        display_input = f"**【{style_key}】**\n\n{user_input}"
        st.session_state.writer_messages.append({"role": "user", "content": display_input})

        with st.chat_message("user"):
            st.markdown(display_input)

        with st.chat_message("assistant"):
            placeholder = st.empty()
            with st.spinner("AI 正在创作..."):
                full_response = generate_text(style_key, user_input, effective_temp, word_count)
                placeholder.markdown(full_response)

        st.session_state.writer_messages.append({"role": "assistant", "content": full_response})
        st.rerun()

    # ---- 底部：导出 + 朗读 ----
    if st.session_state.writer_messages:
        st.divider()
        last_text = ""
        for m in reversed(st.session_state.writer_messages):
            if m["role"] == "assistant":
                last_text = m["content"]
                break
        if last_text:
            col_dl, col_voice = st.columns(2)
            with col_dl:
                st.download_button(
                    label="⬇️ 导出为文本",
                    data=last_text,
                    file_name="ai_writing.txt",
                    mime="text/plain",
                    use_container_width=True,
                )
            with col_voice:
                with st.expander("🔊 朗读设置", expanded=False):
                    voice_id = st.selectbox("音色", list(VOICES.keys()), format_func=lambda k: VOICES[k], key="writer_voice")
                    speed = st.slider("语速", 0.5, 2.0, 1.0, 0.1, key="writer_voice_speed")
                    if st.button("🔊 朗读最新作品", use_container_width=True):
                        with st.spinner("正在合成语音..."):
                            audio = synthesize_speech(last_text, voice_id=voice_id, speed=speed)
                            if audio:
                                st.session_state.writer_audio = audio
                            else:
                                st.error("语音合成失败")
                        st.rerun()

                if st.session_state.get("writer_audio"):
                    st.audio(st.session_state.writer_audio, format="audio/mp3")
                    st.download_button(
                        label="⬇️ 下载音频",
                        data=st.session_state.writer_audio,
                        file_name="ai_writing_voice.mp3",
                        mime="audio/mp3",
                        use_container_width=True,
                    )

