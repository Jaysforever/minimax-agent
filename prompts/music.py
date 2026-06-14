"""
AI 音乐与歌词创作助手 — 预设提示词。
"""

PROMPTS_DICT = {
    # 歌词生成 System Prompt
    "system_prompt": (
        "你是一位顶尖的音乐作词人，精通流行、摇滚、民谣、R&B、电子、嘻哈、爵士等所有主流音乐风格。\n\n"
        "## 创作要求\n"
        "1. 按「[主歌] → [副歌] → [主歌] → [副歌] → [桥段] → [副歌]」的经典结构创作\n"
        "2. 每段 2-4 行，每行 10-16 字，段落之间空一行\n"
        "3. 副歌应重复且有记忆点，两段副歌保持相同\n"
        "4. 押韵自然，不强行凑韵脚\n"
        "5. 歌词富有画面感和情感张力\n"
    ),

    # 各风格的生成指令
    "style_pop": (
        "请创作一首流行乐（Pop）风格的歌词。\n"
        "特点：旋律感强、易于传唱、情感直白、副歌记忆点突出。\n"
        "主题：{theme}\n情感基调：{emotion}"
    ),

    "style_rock": (
        "请创作一首摇滚（Rock）风格的歌词。\n"
        "特点：力度感强、节奏鲜明、歌词带有反叛或热血气质。\n"
        "主题：{theme}\n情感基调：{emotion}"
    ),

    "style_ballad": (
        "请创作一首民谣（Folk/Ballad）风格的歌词。\n"
        "特点：叙事性强、语言朴实真诚、充满生活气息和画面感。\n"
        "主题：{theme}\n情感基调：{emotion}"
    ),

    "style_rnb": (
        "请创作一首 R&B / 蓝调（Blues）风格的歌词。\n"
        "特点：节奏感强、情感细腻深沉、带有灵魂乐的转音韵味。\n"
        "主题：{theme}\n情感基调：{emotion}"
    ),

    "style_electronic": (
        "请创作一首电子音乐（Electronic）风格的歌词。\n"
        "特点：简洁重复、节奏感强、适合舞曲或氛围音乐，强调氛围感。\n"
        "主题：{theme}\n情感基调：{emotion}"
    ),

    "style_hiphop": (
        "请创作一首嘻哈（Hip-Hop）风格的歌词。\n"
        "特点：节奏感强、押韵密集、带有态度和叙事性，Punchline 有力。\n"
        "主题：{theme}\n情感基调：{emotion}"
    ),

    "style_jazz": (
        "请创作一首爵士（Jazz）风格的歌词。\n"
        "特点：自由即兴、语言优雅含蓄、充满都市感和夜晚氛围。\n"
        "主题：{theme}\n情感基调：{emotion}"
    ),
}

# 风格选项：{key: 显示名称}
STYLE_OPTIONS = {
    "style_pop": "流行 Pop",
    "style_rock": "摇滚 Rock",
    "style_ballad": "民谣 Ballad",
    "style_rnb": "R&B / 蓝调",
    "style_electronic": "电子 Electronic",
    "style_hiphop": "嘻哈 Hip-Hop",
    "style_jazz": "爵士 Jazz",
}

EMOTION_OPTIONS = [
    "快乐 / 欢快", "悲伤 / 忧郁", "热血 / 激昂",
    "浪漫 / 甜蜜", "孤独 / 寂寥", "励志 / 向上",
    "愤怒 / 宣泄", "平静 / 治愈",
]
