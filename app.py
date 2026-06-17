"""
AI-Tools 主入口。
通过侧边栏路由到不同的 AI 工具。
"""

import sys
import streamlit as st

# 页面配置
st.set_page_config(page_title="Jay-AI-Tools", page_icon="🤖", layout="wide")

# ---- 工具注册表 ----
# 每个工具：{id, title, icon, module}
TOOLS = [
    {"id": "research", "title": "科研助手", "icon": "🔬", "module": "tools.research_assistant"},
    {"id": "writer", "title": "创作助手", "icon": "✍️", "module": "tools.writer"},
    {"id": "math_solver", "title": "数学解题", "icon": "🧮", "module": "tools.math_solver"},
    {"id": "image_generator", "title": "AI生图", "icon": "🎨", "module": "tools.image_generator"},
    {"id": "music_generator", "title": "音乐创作", "icon": "🎵", "module": "tools.music_generator"},
    {"id": "game_creator", "title": "游戏创作", "icon": "🎮", "module": "tools.game_creator"},
]


def render_sidebar() -> str:
    """渲染侧边栏，返回当前选中的工具 id。"""
    with st.sidebar:
        st.title("Jay-AI-Tools")
        st.caption("多功能 AI agent")

        st.divider()

        # 工具导航
        tool_ids = [t["id"] for t in TOOLS]
        tool_labels = [f'{t["icon"]}  {t["title"]}' for t in TOOLS]

        selected_index = st.radio(
            "选择工具",
            range(len(TOOLS)),
            format_func=lambda i: tool_labels[i],
            key="tool_selector",
        )

        selected_id = tool_ids[selected_index]

        st.divider()

        # 环境状态指示
        import os
        from dotenv import load_dotenv
        load_dotenv()

        has_key = bool(os.getenv("MINIMAX_API_KEY"))
        if has_key:
            st.success("API 密钥已配置")
        else:
            st.error("未检测到 MINIMAX_API_KEY，请在 .env 文件中配置")

        return selected_id


def main():
    tool_id = render_sidebar()

    # 动态导入并渲染对应工具
    tool = next(t for t in TOOLS if t["id"] == tool_id)
    module = __import__(tool["module"], fromlist=["render"])
    module.render()


if __name__ == "__main__":
    main()
