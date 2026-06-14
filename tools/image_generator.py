"""
AI 视觉创作（M3 时代重写版）。
流程：输入描述 → AI 增强提示词（可编辑）→ 生成图片 → 多轮对话修图（i2i 智能回退）
"""

import os
import re
import base64
import requests
import streamlit as st
from core.model import chat
from prompts.image import PROMPTS_DICT, STYLE_SUFFIXES, ASPECT_RATIOS, STYLE_LABELS

IMAGE_API_URL = "https://api.minimaxi.com/v1/image_generation"
PROMPT_MAX_CHARS = 1500  # 官方限制


def _get_api_key() -> str:
    return os.getenv("MINIMAX_API_KEY", "")


# ======================
# Prompt 增强（步骤 1）
# ======================
def enhance_prompt(user_input: str, style: str, has_reference: bool = False) -> str:
    """调用文本 API 将简短中文描述扩展为专业英文绘画提示词。"""
    style_suffix = STYLE_SUFFIXES.get(style, STYLE_SUFFIXES["摄影写实"])
    system_prompt = PROMPTS_DICT["enhancer_system"].format(style_suffix=style_suffix)
    user_prompt = PROMPTS_DICT["enhancer_user"].format(user_input=user_input)

    # 如果有参考图，在 prompt 里告诉 AI：保留主体形象
    if has_reference:
        user_prompt = (
            "[用户上传了一张参考图，请生成保留该图主体形象的英文 prompt]\n\n"
            + user_prompt
        )

    messages = [{"role": "user", "content": user_prompt}]
    full_text = ""
    for chunk in chat(messages=messages, system_prompt=system_prompt):
        full_text += chunk
    return full_text.strip()


# ======================
# 修改指令增强（对话修图）
# ======================
def enhance_modification(user_request: str, current_prompt: str, style_suffix: str) -> str:
    """
    将用户的中文修改指令（如"改成夜晚"）转化为英文 prompt。
    保留原 prompt 的核心主体描述，只追加/修改变化部分。
    """
    system_prompt = (
        "You are an expert AI image prompt engineer. "
        "The user has an existing image prompt and wants to modify it. "
        "Output ONLY the new complete English prompt, no explanations, no markdown. "
        "Keep the main subject consistent, only apply the requested changes. "
        f"Style suffix: {style_suffix}. "
        "Keep output under 1500 characters."
    )
    user_prompt = (
        f"Current prompt:\n{current_prompt}\n\n"
        f"User's modification request (in Chinese): {user_request}\n\n"
        "Output the new complete prompt:"
    )

    messages = [{"role": "user", "content": user_prompt}]
    full_text = ""
    for chunk in chat(messages=messages, system_prompt=system_prompt):
        full_text += chunk
    return full_text.strip()


# ======================
# 图生图（i2i）智能调用
# ======================
def _download_image_as_data_url(url: str) -> str | None:
    """下载图片并转为 data URL（用于 i2i 主体参考）。"""
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            return None
        b64 = base64.b64encode(resp.content).decode("utf-8")
        # 简单通过 Content-Type 判断格式，默认 jpeg
        content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
        return f"data:{content_type};base64,{b64}"
    except Exception:
        return None


def generate_image(
    prompt: str,
    aspect_ratio: str,
    n: int = 1,
    reference_image_url: str = "",
) -> list[str] | None:
    """
    调用 MiniMax image-01 生成图片。
    - reference_image_url 为空：纯文生图
    - reference_image_url 非空：i2i（带主体参考）
    返回图片 URL 列表，失败返回 None。
    """
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "image-01",
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "n": n,
        "response_format": "url",
        "prompt_optimizer": True,
    }

    if reference_image_url:
        # 智能回退：先尝试用公网 URL，失败再下载转 base64
        subject_ref = {"type": "character", "image_file": reference_image_url}
        payload["subject_reference"] = [subject_ref]

    print(f"[generate_image] prompt length={len(prompt)}, has_ref={bool(reference_image_url)}")

    try:
        resp = requests.post(IMAGE_API_URL, headers=headers, json=payload, timeout=120)
        print(f"[generate_image] status={resp.status_code} body={resp.text[:200]}")

        if resp.status_code != 200:
            st.error(f"图像生成 API 错误 ({resp.status_code}): {resp.text[:500]}")
            return None

        result = resp.json()
        base = result.get("base_resp", {})
        if base.get("status_code") != 0:
            # i2i 失败：自动回退到纯文本再生
            if reference_image_url:
                st.warning(
                    f"⚠️ 主体参考模式失败（{base.get('status_msg', '未知')}），"
                    f"已自动回退到纯文本生成"
                )
                return generate_image(prompt=prompt, aspect_ratio=aspect_ratio, n=n, reference_image_url="")
            st.error(f"图像生成失败: {base.get('status_msg', '未知错误')}")
            return None

        urls = result.get("data", {}).get("image_urls", [])
        return urls if urls else None
    except Exception as e:
        st.error(f"图像生成异常: {e}")
        return None


# ======================
# UI 主流程
# ======================
def render():
    st.title("AI 生图")
    st.caption("可选上传参考图 → 输入描述 → AI 增强提示词 → 生成图片 → 多轮对话修图")

    # ---- 会话状态 ----
    defaults = {
        "img_ref_uploaded_b64": "",        # 上传参考图的 data URL（用于 i2i 主体参考）
        "img_ref_uploaded_name": "",       # 上传参考图的文件名
        "img_original_input": "",          # 用户最初的中文描述
        "img_style": STYLE_LABELS[0],
        "img_ratio": list(ASPECT_RATIOS.keys())[0],
        "img_n": 1,
        "img_enhanced_prompt": "",         # AI 增强后的英文 prompt
        "img_current_url": "",             # 当前选中的图片 URL
        "img_history": [],                 # 历史图片：[(url, prompt, time), ...]
        "img_chat": [],                    # 多轮对话：[(role, content, image_url), ...]
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # ---- 侧边栏：参数 ----
    with st.sidebar:
        st.subheader("⚙️ 生成参数")
        style = st.selectbox("艺术风格", STYLE_LABELS, key="img_style_select")
        ratio_label = st.selectbox(
            "画面比例", list(ASPECT_RATIOS.keys()), key="img_ratio_select"
        )
        num_images = st.slider("生成数量", 1, 4, 1, key="img_n_select")

        st.divider()
        if st.button("🔄 重新开始", use_container_width=True):
            for key in defaults:
                st.session_state[key] = defaults[key]
            st.rerun()

    # ================================
    # Step 0：上传参考图（可选）
    # ================================
    st.subheader("Step 0 — 上传参考图（可选）")
    st.caption("💡 上传一张参考图，AI 会保留主体形象；不传也能正常创作。")

    col_upload, col_preview = st.columns([1, 1])
    with col_upload:
        ref_file = st.file_uploader(
            "选择图片文件",
            type=["png", "jpg", "jpeg", "webp"],
            key="img_ref_upload",
            help="支持的格式：PNG, JPG, JPEG, WebP（≤10MB）",
        )
        if ref_file and ref_file.name != st.session_state.img_ref_uploaded_name:
            # 新文件：转为 data URL 存到 session_state
            file_bytes = ref_file.getvalue()
            if len(file_bytes) > 10 * 1024 * 1024:
                st.error("❌ 文件超过 10MB，请压缩后重试")
            else:
                b64 = base64.b64encode(file_bytes).decode("utf-8")
                ext = ref_file.name.split(".")[-1].lower()
                mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
                st.session_state.img_ref_uploaded_b64 = f"data:{mime};base64,{b64}"
                st.session_state.img_ref_uploaded_name = ref_file.name
                st.success(f"✅ 已加载 {ref_file.name}（{len(file_bytes) // 1024} KB）")
                st.rerun()

        if st.session_state.img_ref_uploaded_b64:
            if st.button("🗑️ 移除参考图", use_container_width=True):
                st.session_state.img_ref_uploaded_b64 = ""
                st.session_state.img_ref_uploaded_name = ""
                st.rerun()

    with col_preview:
        if st.session_state.img_ref_uploaded_b64:
            st.image(
                st.session_state.img_ref_uploaded_b64,
                caption=f"📎 {st.session_state.img_ref_uploaded_name}",
                use_container_width=True,
            )
        else:
            st.info("未上传参考图\n（可上传一张角色图让 AI 保留形象）")

    # ================================
    # Step 1：输入描述
    # ================================
    st.subheader("Step 1 — 输入画面描述")
    user_input = st.text_area(
        "用中文描述你想生成的画面",
        placeholder="例如：一只可爱的奶龙在太空漂浮，背景是星空...",
        height=80,
        key="img_input",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        enhance_btn = st.button(
            "🎨 增强提示词",
            type="primary",
            disabled=not user_input.strip(),
            use_container_width=True,
        )

    if enhance_btn:
        st.session_state.img_original_input = user_input
        with st.spinner("AI 正在优化提示词..."):
            has_ref = bool(st.session_state.img_ref_uploaded_b64)
            enhanced = enhance_prompt(
                user_input, st.session_state.img_style, has_reference=has_ref
            )
            if len(enhanced) > PROMPT_MAX_CHARS:
                st.warning(f"⚠️ 增强后 {len(enhanced)} 字符，已自动截断到 {PROMPT_MAX_CHARS}")
                enhanced = enhanced[:PROMPT_MAX_CHARS]
            st.session_state.img_enhanced_prompt = enhanced
        st.rerun()

    # ================================
    # Step 2：编辑增强后的提示词
    # ================================
    if st.session_state.img_enhanced_prompt:
        st.divider()
        st.subheader("Step 2 — 调整提示词（可编辑）")
        edited_prompt = st.text_area(
            "AI 增强的英文提示词，你可以直接修改：",
            value=st.session_state.img_enhanced_prompt,
            height=180,
            key="img_edited_prompt",
        )

        # 同步到 session_state
        st.session_state.img_enhanced_prompt = edited_prompt

        if st.button(
            f"🖼️ 用此提示词生成 {st.session_state.img_n_select} 张图片",
            type="primary",
            use_container_width=True,
        ):
            aspect_ratio = ASPECT_RATIOS[st.session_state.img_ratio_select]
            with st.spinner(f"正在生成 {st.session_state.img_n_select} 张图片..."):
                # 如果有上传参考图，传给 API 作为主体参考
                ref_url = st.session_state.img_ref_uploaded_b64 or ""
                urls = generate_image(
                    prompt=edited_prompt,
                    aspect_ratio=aspect_ratio,
                    n=st.session_state.img_n_select,
                    reference_image_url=ref_url,
                )
                if urls:
                    # 把首张作为当前图
                    st.session_state.img_current_url = urls[0]
                    # 加入历史
                    from datetime import datetime
                    st.session_state.img_history.insert(
                        0,
                        {
                            "url": urls[0],
                            "prompt": edited_prompt,
                            "time": datetime.now().strftime("%H:%M:%S"),
                        },
                    )
                    # 清空对话历史（开启新一轮对话）
                    st.session_state.img_chat = []
                    st.success(f"✅ 已生成 {len(urls)} 张图片")
            st.rerun()

    # ================================
    # Step 3：当前图片 + 历史画廊
    # ================================
    if st.session_state.img_current_url or st.session_state.img_history:
        st.divider()
        st.subheader("Step 3 — 当前图片")

        if st.session_state.img_current_url:
            col1, col2 = st.columns([2, 1])
            with col1:
                st.image(st.session_state.img_current_url, use_container_width=True)
            with col2:
                st.caption("📋 当前提示词：")
                st.code(st.session_state.img_current_url[:0] or "", language=None)  # placeholder
                with st.expander("查看完整 prompt", expanded=False):
                    # 找到当前 url 对应的 prompt
                    current_prompt = ""
                    for item in st.session_state.img_history:
                        if item["url"] == st.session_state.img_current_url:
                            current_prompt = item["prompt"]
                            break
                    st.code(current_prompt, language=None, wrap_lines=True)

                st.download_button(
                    label="⬇️ 下载当前图片",
                    data=requests.get(st.session_state.img_current_url, timeout=30).content,
                    file_name="ai_image.png",
                    mime="image/png",
                    use_container_width=True,
                )

                if st.button("🗑️ 选其他图片", use_container_width=True):
                    st.session_state.img_current_url = ""
                    st.rerun()

        # ---- 历史画廊 ----
        if len(st.session_state.img_history) > 1:
            st.divider()
            st.subheader(f"🖼️ 历史画廊（{len(st.session_state.img_history)} 张）")
            history_cols = st.columns(4)
            for idx, item in enumerate(st.session_state.img_history[:8]):  # 最多显示 8 张
                with history_cols[idx % 4]:
                    # 当前图加边框
                    is_current = item["url"] == st.session_state.img_current_url
                    if st.button(
                        f"{'⭐ ' if is_current else ''}版本 {idx+1}\n{item['time']}",
                        key=f"history_{idx}",
                        use_container_width=True,
                        disabled=is_current,
                    ):
                        st.session_state.img_current_url = item["url"]
                        st.rerun()
                    st.image(item["url"], use_container_width=True)

    # ================================
    # Step 4：多轮对话修图
    # ================================
    if st.session_state.img_current_url:
        st.divider()
        st.subheader("Step 4 — 对话修图")
        st.caption("用自然语言描述你想如何修改图片，AI 会重新生成。系统会自动尝试保留主体。")

        # ---- 显示对话历史 ----
        for msg in st.session_state.img_chat:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("image_url"):
                    st.image(msg["image_url"], width=300)

        # ---- 聊天输入 ----
        if user_request := st.chat_input("例如：把它改成夜晚场景 / 换成油画风格 / 加个朋友"):
            # 添加用户消息
            st.session_state.img_chat.append({
                "role": "user",
                "content": user_request,
                "image_url": None,
            })

            with st.chat_message("user"):
                st.markdown(user_request)

            # AI 思考 + 生成
            with st.chat_message("assistant"):
                with st.spinner("AI 正在理解修改意图..."):
                    # 找到当前 prompt
                    current_prompt = ""
                    for item in st.session_state.img_history:
                        if item["url"] == st.session_state.img_current_url:
                            current_prompt = item["prompt"]
                            break

                    style_suffix = STYLE_SUFFIXES.get(
                        st.session_state.img_style, STYLE_SUFFIXES["摄影写实"]
                    )
                    new_prompt = enhance_modification(
                        user_request, current_prompt, style_suffix
                    )
                    if len(new_prompt) > PROMPT_MAX_CHARS:
                        new_prompt = new_prompt[:PROMPT_MAX_CHARS]
                    st.caption("📝 新提示词：")
                    st.code(new_prompt, language=None, wrap_lines=True)

                with st.spinner("正在生成新图片..."):
                    aspect_ratio = ASPECT_RATIOS[st.session_state.img_ratio_select]
                    new_urls = generate_image(
                        prompt=new_prompt,
                        aspect_ratio=aspect_ratio,
                        n=1,
                        reference_image_url=st.session_state.img_current_url,  # 传当前图作为主体参考
                    )
                    if new_urls:
                        st.image(new_urls[0], width=300)
                        # 更新当前图
                        st.session_state.img_current_url = new_urls[0]
                        from datetime import datetime
                        st.session_state.img_history.insert(
                            0,
                            {
                                "url": new_urls[0],
                                "prompt": new_prompt,
                                "time": datetime.now().strftime("%H:%M:%S"),
                            },
                        )
                        # 添加助手消息
                        st.session_state.img_chat.append({
                            "role": "assistant",
                            "content": f"已根据你的要求「{user_request}」生成新图片。",
                            "image_url": new_urls[0],
                        })
                    else:
                        st.session_state.img_chat.append({
                            "role": "assistant",
                            "content": "❌ 图片生成失败，请重试或调整描述。",
                            "image_url": None,
                        })
            st.rerun()
