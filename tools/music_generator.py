"""
AI 音乐与歌词创作助手（M3 时代重写版）。
两种模式：
  1. 歌词创作：从零生成歌词 → 编辑 → 生成音乐
  2. 翻唱：上传音频 → 分析结构 → 替换歌词 → 生成音乐
"""

import os
import re
import base64
import requests
import streamlit as st
from core.model import chat
from prompts.music import PROMPTS_DICT, STYLE_OPTIONS, EMOTION_OPTIONS

# MiniMax 官方端点
LYRICS_GENERATION_URL = "https://api.minimaxi.com/v1/lyrics_generation"
MUSIC_GENERATION_URL = "https://api.minimaxi.com/v1/music_generation"
COVER_PREPROCESS_URL = "https://api.minimaxi.com/v1/music_cover_preprocess"

LYRICS_MAX_CHARS = 3500

SECTION_LABELS = {
    "[主歌]": "主歌", "[副歌]": "副歌", "[桥段]": "桥段",
    "[verse]": "主歌", "[chorus]": "副歌", "[bridge]": "桥段",
    "[Verse]": "主歌", "[Chorus]": "副歌", "[Bridge]": "桥段",
    "[Intro]": "前奏", "[Outro]": "尾声", "[Interlude]": "间奏",
}

GENERATION_MODES = {
    "music-2.6-free": "music-2.6-free（限免版，推荐先用）",
    "music-2.6": "music-2.6（付费版，RPM 更高）",
    "music-cover-free": "music-cover-free（限免翻唱）",
    "music-cover": "music-cover（付费翻唱）",
}

def trim_audio(audio_bytes: bytes, start_sec: float, end_sec: float, format: str = "mp3") -> bytes | None:
    """将音频截断到指定时间段，返回截断后的音频字节。"""
    try:
        from pydub import AudioSegment
        import io

        audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
        start_ms = int(start_sec * 1000)
        end_ms = int(end_sec * 1000)
        trimmed = audio[start_ms:end_ms]

        buf = io.BytesIO()
        trimmed.export(buf, format=format)
        return buf.getvalue()
    except Exception as e:
        st.error(f"音频截断失败: {e}")
        return None


SEGMENT_LABEL_MAP = {
    "intro": "前奏", "verse": "主歌", "chorus": "副歌",
    "bridge": "桥段", "outro": "尾声", "inst": "间奏", "silence": "静音",
}


# ====================== 工具函数 ======================

def _get_api_key() -> str:
    return os.getenv("MINIMAX_API_KEY", "")


def _music_headers() -> dict:
    return {"Authorization": f"Bearer {_get_api_key()}", "Content-Type": "application/json"}


def parse_lyrics_sections(text: str) -> list[tuple[str, str]]:
    """将歌词按结构标签拆分。"""
    pattern = r"(\[(?:主歌|副歌|桥段|Verse|Chorus|Bridge|Intro|Outro|Interlude|Pre-Chorus|Post-Chorus|Hook|Drop|Solo|Build-up|Instrumental|Breakdown|Break|Transition|Pre Chorus|Post Chorus|Build Up|Inst)(?:\s*\d*)\])"
    parts = re.split(pattern, text, flags=re.IGNORECASE)
    sections = []
    i = 0
    while i < len(parts):
        if parts[i] in SECTION_LABELS or re.match(r"\[.*\]", parts[i]):
            label = parts[i]
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            if body:
                sections.append((label, body))
            i += 2
        else:
            i += 1
    if not sections and text.strip():
        sections = [("[完整歌词]", text.strip())]
    return sections


def parse_structure_and_lyrics(structure_result: str, formatted_lyrics: str) -> list[dict]:
    """将 structure_result 和 formatted_lyrics 关联为分段列表。"""
    import json
    try:
        structure = json.loads(structure_result) if isinstance(structure_result, str) else structure_result
    except (json.JSONDecodeError, TypeError):
        structure = {"segments": []}
    segments = structure.get("segments", [])
    lyrics_sections = parse_lyrics_sections(formatted_lyrics)
    result = []
    lyrics_idx = 0
    for seg_idx, seg in enumerate(segments):
        label = seg.get("label", "unknown")
        label_cn = SEGMENT_LABEL_MAP.get(label, label)
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        lyrics_text = ""
        if label not in ("inst", "silence"):
            if lyrics_idx < len(lyrics_sections):
                _, lyrics_text = lyrics_sections[lyrics_idx]
                lyrics_idx += 1
        result.append({"label": label, "label_cn": label_cn, "start": start, "end": end, "lyrics": lyrics_text, "index": seg_idx})
    return result


def generate_lyrics_via_api(prompt: str, title: str = "") -> dict | None:
    """调用官方 lyrics_generation 端点生成歌词。"""
    payload = {"mode": "write_full_song", "prompt": prompt}
    if title:
        payload["title"] = title
    try:
        resp = requests.post(LYRICS_GENERATION_URL, headers=_music_headers(), json=payload, timeout=120)
        if resp.status_code != 200:
            st.error(f"歌词生成 API 失败 ({resp.status_code}): {resp.text[:500]}")
            return None
        result = resp.json()
        base = result.get("base_resp", {})
        if base.get("status_code") != 0:
            st.error(f"歌词生成失败: {base.get('status_msg', '未知错误')}")
            return None
        return {"song_title": result.get("song_title", ""), "lyrics": result.get("lyrics", ""), "style_tags": result.get("style_tags", "")}
    except Exception as e:
        st.error(f"歌词生成异常: {e}")
        return None


def generate_lyrics_legacy(style_key: str, theme: str, emotion: str) -> str:
    """备用方案：调用文本 API 生成歌词。"""
    system_prompt = PROMPTS_DICT["system_prompt"]
    template = PROMPTS_DICT.get(style_key, PROMPTS_DICT["style_pop"])
    user_prompt = template.format(theme=theme, emotion=emotion)
    messages = [{"role": "user", "content": user_prompt}]
    full_text = ""
    for chunk in chat(messages=messages, system_prompt=system_prompt):
        full_text += chunk
    return full_text


def cover_preprocess(audio_base64: str) -> dict | None:
    """两步翻唱第一步：预处理参考音频。"""
    headers = _music_headers()
    payload = {"model": "music-cover", "audio_base64": audio_base64}
    try:
        resp = requests.post(COVER_PREPROCESS_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code != 200:
            st.error(f"音频预处理失败 ({resp.status_code}): {resp.text[:500]}")
            return None
        result = resp.json()
        base = result.get("base_resp", {})
        if base.get("status_code") != 0:
            st.error(f"音频预处理失败: {base.get('status_msg', '未知错误')}")
            return None
        return {"cover_feature_id": result.get("cover_feature_id", ""), "formatted_lyrics": result.get("formatted_lyrics", ""), "audio_duration": result.get("audio_duration", 0), "structure_result": result.get("structure_result", "")}
    except Exception as e:
        st.error(f"音频预处理异常: {e}")
        return None


def generate_music(model: str, lyrics: str, prompt: str = "", is_instrumental: bool = False, audio_base64: str = "", cover_feature_id: str = "", lyrics_optimizer: bool = False) -> bytes | None:
    """调用 music_generation API 生成音乐。"""
    payload = {"model": model, "stream": False, "output_format": "hex", "audio_setting": {"sample_rate": 44100, "bitrate": 256000, "format": "mp3"}}

    if "cover" in model:
        if audio_base64:
            payload["audio_base64"] = audio_base64
        elif cover_feature_id:
            payload["cover_feature_id"] = cover_feature_id
        else:
            st.error("翻唱模式需要上传参考音频或提供 cover_feature_id")
            return None
        if prompt:
            payload["prompt"] = prompt
        COVER_LYRICS_MAX = 1000
        if lyrics:
            if len(lyrics) > COVER_LYRICS_MAX:
                st.warning(f"⚠️ 歌词 {len(lyrics)} 字符超出翻唱模式上限 {COVER_LYRICS_MAX}，已自动截断")
                lyrics = lyrics[:COVER_LYRICS_MAX]
            payload["lyrics"] = lyrics
    else:
        payload["is_instrumental"] = is_instrumental
        if prompt:
            payload["prompt"] = prompt
        if is_instrumental:
            if lyrics and len(lyrics) <= LYRICS_MAX_CHARS:
                payload["lyrics"] = lyrics
        else:
            if not lyrics:
                st.error("非纯音乐模式需要提供歌词")
                return None
            payload["lyrics"] = lyrics[:LYRICS_MAX_CHARS] if len(lyrics) > LYRICS_MAX_CHARS else lyrics
            payload["lyrics_optimizer"] = lyrics_optimizer

    try:
        resp = requests.post(MUSIC_GENERATION_URL, headers=_music_headers(), json=payload, timeout=300)
        if resp.status_code != 200:
            st.error(f"音乐生成失败 ({resp.status_code}): {resp.text[:500]}")
            return None
        result = resp.json()
        base = result.get("base_resp", {})
        if base.get("status_code") != 0:
            st.error(f"音乐生成失败: {base.get('status_msg', '未知错误')}")
            return None
        data = result.get("data", {})
        audio_hex = data.get("audio", "")
        if audio_hex:
            return bytes.fromhex(audio_hex)
        st.error("音乐生成返回了空音频数据")
        return None
    except Exception as e:
        st.error(f"音乐生成异常: {e}")
        return None


def render_with_audio(audio_bytes: bytes, title: str = "生成的音乐"):
    """渲染音频播放器和下载按钮。"""
    st.divider()
    st.subheader(f"🎧 {title}")
    st.audio(audio_bytes, format="audio/mp3")
    st.download_button(label="⬇️ 下载音频", data=audio_bytes, file_name=f"{title}.mp3", mime="audio/mp3", use_container_width=True)


# ====================== 模式 1：歌词创作 ======================

def _render_create_mode():
    """歌词创作模式：从零生成歌词 → 编辑 → 生成音乐。"""
    st.subheader("📝 Step 1 — 生成歌词")

    mode = st.radio("歌词生成方式", ["官方 lyrics_generation 端点（推荐）", "使用旧版提示词模板（备用）"], horizontal=True, key="lyrics_mode")
    col1, col2, col3 = st.columns(3)
    with col1:
        song_title = st.text_input("歌名（可选）", placeholder="留空则自动生成", key="song_title")
    with col2:
        style = st.selectbox("音乐风格", STYLE_OPTIONS, format_func=lambda k: STYLE_OPTIONS[k], key="music_style")
    with col3:
        emotion = st.selectbox("情感基调", EMOTION_OPTIONS, key="music_emotion")
    theme = st.text_input("创作主题 / 描述", placeholder="例如：夏日海边轻快情歌、独立民谣...", key="music_theme")

    if st.button("🎵 生成歌词", type="primary", key="btn_generate_lyrics", disabled=not theme.strip()):
        with st.spinner("AI 正在创作歌词..."):
            if mode.startswith("官方"):
                prompt = f"{style}, {emotion}, {theme}"
                result = generate_lyrics_via_api(prompt=prompt, title=song_title)
                if result:
                    st.session_state.music_song_title = result["song_title"]
                    st.session_state.music_lyrics = result["lyrics"]
                    st.session_state.music_style_tags = result["style_tags"]
                    st.session_state.music_audio_bytes = None
            else:
                lyrics = generate_lyrics_legacy(style, theme, emotion)
                st.session_state.music_song_title = song_title or theme
                st.session_state.music_lyrics = lyrics
                st.session_state.music_style_tags = ""
                st.session_state.music_audio_bytes = None
        st.rerun()

    # Step 2：编辑歌词
    if st.session_state.music_lyrics:
        st.divider()
        st.subheader("📝 Step 2 — 编辑歌词")
        st.caption("💡 生成的歌词可以自由修改，改好后再生成音乐")

        edited_title = st.text_input("歌名", value=st.session_state.music_song_title, key="edited_song_title")
        st.session_state.music_song_title = edited_title

        edited_lyrics = st.text_area("歌词内容（可自由编辑）", value=st.session_state.music_lyrics, height=300, key="edited_lyrics", help="支持结构标签：[Verse] [Chorus] [Bridge] [Intro] [Outro] 等")
        st.session_state.music_lyrics = edited_lyrics

        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.caption(f"📝 共 {len(edited_lyrics)} 字符（上限 {LYRICS_MAX_CHARS}）")
        with col_s2:
            if st.session_state.music_style_tags:
                st.caption(f"🏷️ 风格标签: {st.session_state.music_style_tags}")

    # Step 3：生成音乐
    if st.session_state.music_lyrics:
        st.divider()
        st.subheader("🎶 Step 3 — 生成音乐")

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            model = st.selectbox("生成模型", list(GENERATION_MODES.keys()), format_func=lambda k: GENERATION_MODES[k], key="create_music_model")
        with col_m2:
            is_instrumental = st.checkbox("🎹 纯音乐（无人声）", key="create_instrumental")

        instrumental_prompt = ""
        if is_instrumental:
            instrumental_prompt = st.text_input("音乐描述", placeholder="例如：流行, 忧郁, 适合在下雨的晚上", key="create_instrumental_prompt")

        # 歌词段落选择
        selected_body = ""
        if not is_instrumental:
            sections = parse_lyrics_sections(st.session_state.music_lyrics)
            if len(sections) > 1:
                section_choices = {f"{label}（{len(body)}字）": (label, body) for label, body in sections}
                section_choices["[完整歌词]"] = ("[完整歌词]", st.session_state.music_lyrics)
                selected_key = st.radio("选择要生成音乐的部分", list(section_choices.keys()), key="create_selected_section")
                _, selected_body = section_choices[selected_key]
            else:
                selected_body = st.session_state.music_lyrics
            st.caption(f"选中歌词: {len(selected_body)} / {LYRICS_MAX_CHARS} 字符")
        else:
            selected_body = ""

        can_generate = (is_instrumental and bool(instrumental_prompt.strip())) or (not is_instrumental and bool(selected_body.strip()))
        if st.button("🎶 生成音乐", type="primary", key="btn_create_generate", disabled=not can_generate):
            with st.spinner("AI 正在生成音乐，可能需要 1-2 分钟..."):
                if is_instrumental:
                    audio_bytes = generate_music(model=model, lyrics="", prompt=instrumental_prompt, is_instrumental=True)
                else:
                    audio_bytes = generate_music(model=model, lyrics=selected_body, lyrics_optimizer=False)
                if audio_bytes:
                    st.session_state.music_audio_bytes = audio_bytes
                    st.success("🎉 音乐生成完成！")
            st.rerun()

    # 播放与下载
    if st.session_state.music_audio_bytes:
        render_with_audio(st.session_state.music_audio_bytes, st.session_state.music_song_title or "ai_music")


# ====================== 模式 2：翻唱 ======================

def _render_cover_mode():
    """翻唱模式：上传音频 → 选时间段 → 截断 → 分析 → 写歌词 → 生成。"""
    st.subheader("🎤 Step 1 — 上传音频")
    st.caption("上传音乐 → 选时间段 → AI 分析 → 写新歌词 → 生成（保留原曲原声）")

    ref_audio = st.file_uploader("选择音频文件", type=["mp3", "wav", "flac"], key="cover_ref_upload")
    if ref_audio:
        audio_bytes = ref_audio.getvalue()
        if len(audio_bytes) > 50 * 1024 * 1024:
            st.error("❌ 文件超过 50MB")
        else:
            st.audio(audio_bytes, format=f"audio/{ref_audio.name.split('.')[-1]}")
            # 保存原始音频
            st.session_state.music_ref_raw_bytes = audio_bytes
            st.session_state.music_ref_audio_name = ref_audio.name

            # 获取音频时长
            try:
                from pydub import AudioSegment
                import io as _io
                audio_seg = AudioSegment.from_file(_io.BytesIO(audio_bytes))
                raw_duration = len(audio_seg) / 1000.0
            except Exception:
                raw_duration = 300  # 兜底

            st.session_state.music_ref_raw_duration = raw_duration
            st.info(f"📊 音频时长: {raw_duration:.1f} 秒")

    # Step 2：选时间段 → 截断
    if st.session_state.get("music_ref_raw_bytes"):
        st.divider()
        st.subheader("⏱️ Step 2 — 选择要翻唱的时间段")

        duration = st.session_state.music_ref_raw_duration

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            start_time = st.number_input("开始时间（秒）", min_value=0.0, max_value=float(duration), value=0.0, step=1.0, key="cover_start_time")
        with col_t2:
            end_time = st.number_input("结束时间（秒）", min_value=start_time + 3, max_value=float(duration), value=min(float(duration), start_time + 30), step=1.0, key="cover_end_time")

        interval = end_time - start_time
        st.caption(f"⏱️ 选中: {int(start_time//60)}:{start_time%60:04.1f} → {int(end_time//60)}:{end_time%60:04.1f}（{interval:.1f} 秒）")

        if st.button("✂️ 截断并分析", type="primary", key="btn_trim_analyze", use_container_width=True):
            with st.spinner("截断音频中..."):
                trimmed = trim_audio(st.session_state.music_ref_raw_bytes, start_time, end_time)
                if trimmed:
                    st.session_state.music_ref_audio_b64 = base64.b64encode(trimmed).decode("utf-8")
                    st.audio(trimmed, format="audio/mp3")
                    st.success(f"✅ 已截断 {interval:.1f} 秒")

                    with st.spinner("正在分析歌曲结构和提取歌词..."):
                        result = cover_preprocess(st.session_state.music_ref_audio_b64)
                        if result:
                            st.session_state.music_cover_feature_id = result["cover_feature_id"]
                            st.session_state.music_cover_orig_lyrics = result["formatted_lyrics"]
                            st.session_state.music_cover_structure = result["structure_result"]
                            st.session_state.music_cover_duration = result["audio_duration"]
                            st.success(f"✅ 分析完成！提取歌词 {len(result['formatted_lyrics'])} 字符")
                        else:
                            st.session_state.music_cover_feature_id = ""
                    st.rerun()

    # Step 3：写歌词
    if st.session_state.get("music_cover_feature_id"):
        st.divider()
        st.subheader("📝 Step 3 — 写歌词")

        # 显示 ASR 提取的歌词（参考）
        orig_lyrics = st.session_state.music_cover_orig_lyrics
        if orig_lyrics.strip():
            with st.expander("📖 ASR 提取的原始歌词（参考）", expanded=False):
                st.code(orig_lyrics, language=None, wrap_lines=True)

        # 显示歌曲结构
        segments = parse_structure_and_lyrics(
            st.session_state.get("music_cover_structure", ""),
            orig_lyrics,
        )
        if segments:
            st.markdown("**🎵 歌曲结构：**")
            parts = []
            for seg in segments:
                s = f"{int(seg['start']//60)}:{seg['start']%60:04.1f}"
                e = f"{int(seg['end']//60)}:{seg['end']%60:04.1f}"
                parts.append(f"`{s}→{e}` {seg['label_cn']}")
            st.markdown(" ｜ ".join(parts))

        # 写歌词
        new_lyrics = st.text_area(
            "📝 输入歌词",
            value=orig_lyrics,
            height=200,
            key="cover_new_lyrics",
            help="这段歌词会用于截断后的音频翻唱",
        )

        # Step 4：生成
        if new_lyrics.strip() and len(new_lyrics.strip()) >= 10:
            st.divider()
            st.subheader("🎶 Step 4 — 生成翻唱")

            col_g1, col_g2 = st.columns(2)
            with col_g1:
                model = st.selectbox("生成模型", ["music-cover-free", "music-cover"], format_func=lambda k: GENERATION_MODES[k], key="cover_gen_model")
            with col_g2:
                cover_prompt = st.text_input("风格描述（可选）", placeholder="例如：保持原风格, 摇滚版", key="cover_gen_prompt")

            st.caption(f"歌词长度: {len(new_lyrics.strip())} / 1000 字符")

            if st.button("🎶 生成翻唱", type="primary", key="btn_cover_generate", use_container_width=True):
                with st.spinner("AI 正在生成翻唱，可能需要 1-2 分钟..."):
                    final_prompt = cover_prompt.strip() if cover_prompt.strip() else "保持原曲风格,用同样的声音演唱新歌词"
                    audio_bytes = generate_music(
                        model=model,
                        lyrics=new_lyrics.strip(),
                        prompt=final_prompt,
                        cover_feature_id=st.session_state.music_cover_feature_id,
                    )
                    if audio_bytes:
                        st.session_state.music_audio_bytes = audio_bytes
                        st.success("🎉 翻唱生成完成！")
                st.rerun()
        elif new_lyrics.strip() and len(new_lyrics.strip()) < 10:
            st.warning("⚠️ 歌词太短（最少 10 字符）")

    # 播放与下载
    if st.session_state.music_audio_bytes:
        render_with_audio(st.session_state.music_audio_bytes, "翻唱结果")


# ====================== 主入口 ======================

def render():
    st.title("🎵 音乐创作")
    st.caption("歌词创作 · 翻唱 · 音乐生成")

    # ---- 会话状态 ----
    defaults = {
        "music_song_title": "", "music_lyrics": "", "music_style_tags": "",
        "music_audio_bytes": None,
        "music_ref_audio_b64": "", "music_ref_audio_name": "",
        "music_cover_feature_id": "", "music_cover_orig_lyrics": "", "music_cover_structure": "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # ---- 模式选择 ----
    tab_create, tab_cover = st.tabs(["📝 歌词创作", "🎤 翻唱"])

    with tab_create:
        st.caption("从零开始：AI 生成歌词 → 编辑 → 生成音乐")
        _render_create_mode()

    with tab_cover:
        st.caption("已有想法：上传音频 → 分析结构 → 替换歌词 → 生成翻唱")
        _render_cover_mode()
