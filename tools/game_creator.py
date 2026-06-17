"""
AI 游戏创作助手。
对话式创作 → 实时看到代码被生成 → 点预览弹出游戏。
"""

import re
import streamlit as st
import streamlit.components.v1 as components
from core.model import chat
from prompts.game import PROMPTS_DICT


def _extract_html(text: str) -> str:
    """从 AI 回复中提取 HTML 代码。"""
    match = re.search(r"```html\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if "<!DOCTYPE html>" in text.lower():
        start = text.lower().find("<!doctype html>")
        end = text.rfind("</html>")
        if end > start:
            return text[start:end + 7]
    if "<html>" in text.lower():
        start = text.lower().find("<html>")
        end = text.rfind("</html>")
        if end > start:
            return text[start:end + 7]
    return text.strip()


@st.dialog("🎮 游戏预览", width="large")
def _show_game_modal(html_code: str):
    """弹窗显示游戏预览，可关闭。"""
    # 把 dialog 强制拉到接近全屏
    st.markdown("""
    <style>
    /* 把弹窗拉到全屏宽 */
    [data-testid="stDialog"] div[role="dialog"] {
        width: 95vw !important;
        max-width: 95vw !important;
    }
    /* 让弹窗更高 */
    [data-testid="stDialog"] div[role="dialog"] > div {
        height: 90vh !important;
    }
    </style>
    """, unsafe_allow_html=True)
    st.caption("操作游戏 → 点右上角 X 关闭弹窗")
    components.html(html_code, height=750, scrolling=False)
    st.download_button(
        label="⬇️ 下载游戏 HTML",
        data=html_code,
        file_name="my_game.html",
        mime="text/html",
        use_container_width=True,
    )


def _generate_game(user_input: str):
    """调用 AI 生成/修改游戏，实时流式显示代码。"""
    # 保存用户消息
    st.session_state.game_chat.append({"role": "user", "content": user_input})

    # 构造 prompt
    if st.session_state.game_code:
        prompt = PROMPTS_DICT["modify_prompt"].format(
            current_code=st.session_state.game_code,
            request=user_input,
        )
    else:
        prompt = PROMPTS_DICT["create_prompt"].format(description=user_input)

    messages = [{"role": "user", "content": prompt}]

    st.markdown("### 📝 实时生成代码中...")

    # ---- 核心：st.write_stream 真正支持流式 UI 更新 ----
    # 不用 markdown 围栏（围栏在 write_stream 中不会触发增量重渲染，会一直空白）
    # 改为流式输出原始 HTML 文本，生成完后再用 st.code() 高亮显示
    def stream_generator():
        for chunk in chat(
            messages=messages,
            system_prompt=PROMPTS_DICT["system_prompt"],
            stream=True,
        ):
            yield chunk

    try:
        full_text = st.write_stream(stream_generator())
    except Exception as e:
        st.error(f"❌ 生成失败：{e}")
        return

    if not full_text:
        st.error("❌ AI 未返回任何内容")
        return

    # ---- 生成完毕：保存 + 完整代码块（带语法高亮）+ 预览按钮 ----
    html_code = _extract_html(full_text)
    if html_code and len(html_code) > 100:
        st.session_state.game_code = html_code
    st.session_state.game_chat.append({"role": "assistant", "content": full_text})

    st.markdown("#### ✅ 生成完成！完整代码：")
    st.code(full_text, language="html")

    st.success("👆 点击下方按钮预览游戏")
    st.balloons()

    if st.button(
        "▶️ 立即预览游戏",
        type="primary",
        key="preview_after_gen",
        use_container_width=True,
    ):
        _show_game_modal(st.session_state.game_code)

    # 不调用 st.rerun() —— 让用户看到预览按钮
    # 用户点击预览/顶部按钮/输入框时会自然触发 rerun


def _do_stream_generate(user_input: str):
    """实际执行流式生成（保留备用）。"""
    _generate_game(user_input)


def render():
    st.title("🎮 游戏创作")
    st.caption("描述你想要的游戏 → 看着代码被实时生成 → 点预览运行")

    # ---- 会话状态 ----
    defaults = {"game_code": "", "game_chat": []}
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # ---- 强制代码块占满全宽（CSS hack） ----
    st.markdown("""
    <style>
    [data-testid="stCodeBlock"] {
        width: 100% !important;
        max-width: 100% !important;
    }
    pre {
        width: 100% !important;
    }
    code, pre code {
        white-space: pre !important;
        word-break: normal !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ---- 快捷模板 ----
    # 注意：必须在 columns 外面调用 _generate_game()，否则 st.code() 会被挤进 1/6 宽的列里
    st.markdown("**快速开始：**")
    t1, t2, t3, t4, t5, t6 = st.columns(6)
    with t1:
        if st.button("🐍 贪吃蛇", use_container_width=True, key="quick_snake"):
            st.session_state._pending_input = "创建一个贪吃蛇游戏"
    with t2:
        if st.button("🧱 俄罗斯方块", use_container_width=True, key="quick_tetris"):
            st.session_state._pending_input = "创建一个俄罗斯方块游戏"
    with t3:
        if st.button("🏓 打砖块", use_container_width=True, key="quick_brick"):
            st.session_state._pending_input = "创建一个打砖块游戏"
    with t4:
        if st.button("🎯 飞镖", use_container_width=True, key="quick_dart"):
            st.session_state._pending_input = "创建一个飞镖射击游戏，点击发射飞镖命中靶心"
    with t5:
        if st.button("🏎️ 赛车", use_container_width=True, key="quick_race"):
            st.session_state._pending_input = "创建一个赛车游戏，左右躲避障碍物"
    with t6:
        if st.button("🃏 翻牌", use_container_width=True, key="quick_card"):
            st.session_state._pending_input = "创建一个记忆翻牌游戏，配对消除"

    # 在 columns 外面真正执行生成
    if getattr(st.session_state, "_pending_input", ""):
        pending = st.session_state._pending_input
        st.session_state._pending_input = ""
        _generate_game(pending)
        return  # 生成中直接返回，避免重复渲染下面的代码块

    st.divider()

    # ---- 代码展示区（占满全宽，最重要的内容） ----
    if st.session_state.game_code:
        # 持久化显示完成的代码
        st.markdown("### 📝 当前代码")
        st.code(st.session_state.game_code, language="html")

        # 预览按钮（占满宽度）
        if st.button("▶️ 预览游戏", type="primary", key="preview_main", use_container_width=True):
            _show_game_modal(st.session_state.game_code)

        # 下载按钮
        st.download_button(
            label="⬇️ 下载游戏 HTML",
            data=st.session_state.game_code,
            file_name="my_game.html",
            mime="text/html",
            use_container_width=True,
        )

        # 显示当前对话历史
        if st.session_state.game_chat:
            with st.expander(f"📜 对话历史（{len(st.session_state.game_chat)//2} 轮）", expanded=False):
                for msg in st.session_state.game_chat:
                    if msg["role"] == "user":
                        st.markdown(f"🧑 **你：** {msg['content']}")
                    else:
                        st.markdown("🤖 **AI：** 已生成新版本代码")
    else:
        st.info("👆 点上方快捷按钮，或在下方输入框描述游戏")

    st.divider()

    # ---- 输入框 ----
    user_input = st.chat_input("💬 描述你想做的游戏，或提出修改意见...（快捷按钮也会直接发到这里）")
    if user_input:
        _generate_game(user_input)

    # ---- 清空按钮 ----
    if st.session_state.game_code or st.session_state.game_chat:
        if st.button("🗑️ 清空对话和代码", use_container_width=True):
            st.session_state.game_code = ""
            st.session_state.game_chat = []
            st.session_state.game_streaming_code = ""
            st.session_state.game_streaming = False
            st.session_state.game_status = ""
            st.rerun()