"""
AI 游戏创作助手。
对话式创作 → 实时运行游戏 → 实时修改。
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


def _generate_game(user_input: str):
    """调用 AI 生成/修改游戏，更新 session_state。"""
    st.session_state.game_chat.append({"role": "user", "content": user_input})

    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("AI 正在创作游戏..."):
            if st.session_state.game_code:
                prompt = PROMPTS_DICT["modify_prompt"].format(
                    current_code=st.session_state.game_code,
                    request=user_input,
                )
            else:
                prompt = PROMPTS_DICT["create_prompt"].format(description=user_input)

            messages = [{"role": "user", "content": prompt}]
            full_text = ""
            for chunk in chat(messages=messages, system_prompt=PROMPTS_DICT["system_prompt"], stream=True):
                full_text += chunk

            html_code = _extract_html(full_text)
            if html_code and len(html_code) > 100:
                st.session_state.game_code = html_code
                st.markdown("✅ 游戏已生成！请在右侧查看 →")
            else:
                st.markdown(full_text)
                st.markdown("⚠️ 未能提取有效游戏代码，请重试")

            st.session_state.game_chat.append({"role": "assistant", "content": full_text})

    st.rerun()


def render():
    st.title("🎮 游戏创作")
    st.caption("描述你想要的游戏 → 右侧实时运行 → 随时对话修改")

    # ---- 会话状态 ----
    defaults = {"game_code": "", "game_chat": []}
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    # ---- 快捷模板（始终显示在顶部） ----
    st.markdown("**快速开始：**")
    t1, t2, t3, t4, t5, t6 = st.columns(6)
    with t1:
        if st.button("🐍 贪吃蛇", use_container_width=True):
            _generate_game("创建一个贪吃蛇游戏")
    with t2:
        if st.button("🧱 俄罗斯方块", use_container_width=True):
            _generate_game("创建一个俄罗斯方块游戏")
    with t3:
        if st.button("🏓 打砖块", use_container_width=True):
            _generate_game("创建一个打砖块游戏")
    with t4:
        if st.button("🎯 飞镖", use_container_width=True):
            _generate_game("创建一个飞镖射击游戏，点击发射飞镖命中靶心")
    with t5:
        if st.button("🏎️ 赛车", use_container_width=True):
            _generate_game("创建一个赛车游戏，左右躲避障碍物")
    with t6:
        if st.button("🃏 翻牌", use_container_width=True):
            _generate_game("创建一个记忆翻牌游戏，配对消除")

    st.divider()

    # ---- 左右布局：左聊天 + 右游戏（游戏占 2/3） ----
    col_chat, col_game = st.columns([1, 2])

    with col_chat:
        st.subheader("💬 对话")

        for msg in st.session_state.game_chat:
            with st.chat_message(msg["role"]):
                if msg["role"] == "user":
                    st.markdown(msg["content"])
                else:
                    st.markdown("✅ 游戏已生成/更新")

        if user_input := st.chat_input("描述游戏或提出修改..."):
            _generate_game(user_input)

        if st.session_state.game_code:
            st.divider()
            col_dl, col_clear = st.columns(2)
            with col_dl:
                st.download_button("⬇️ 下载", data=st.session_state.game_code, file_name="my_game.html", mime="text/html", use_container_width=True)
            with col_clear:
                if st.button("🗑️ 清空", use_container_width=True):
                    st.session_state.game_code = ""
                    st.session_state.game_chat = []
                    st.rerun()

    with col_game:
        st.subheader("🎮 游戏预览")
        if st.session_state.game_code:
            components.html(st.session_state.game_code, height=700, scrolling=False)
        else:
            st.info("👆 点击上方快捷按钮，或在左侧输入框描述你想要的游戏")
