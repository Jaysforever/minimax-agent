"""
AI 视觉创作 — 风格后缀与 Prompt 增强模板。
"""

PROMPTS_DICT = {
    # Prompt 增强 System Prompt
    "enhancer_system": (
        "你是一位世界级的 AI 绘画提示词工程师，精通 Midjourney、Stable Diffusion、DALL-E 等模型的 Prompt 编写。\n\n"
        "## 任务\n"
        "将用户的简单描述扩展为一段专业的英文绘画提示词。\n\n"
        "## 要求\n"
        "1. 输出**纯英文**提示词（生图模型对英文理解最佳）\n"
        "2. 结构：主体描述 → 环境/场景 → 构图/视角 → 光影/色彩 → 风格/画质\n"
        "3. 提示词控制在 200 词以内，用逗号分隔关键词\n"
        "4. 末尾必须包含以下风格后缀："
        "{style_suffix}\n\n"
        "5. 只输出提示词本身，不要任何解释或 Markdown\n"
        "6. 不要用引号包裹输出"
    ),

    "enhancer_user": "请将以下描述扩展为专业的 AI 绘画提示词：\n{user_input}",
}

# 艺术风格 → Prompt 后缀
STYLE_SUFFIXES = {
    "摄影写实": (
        "photorealistic, hyperrealistic, 8k resolution, highly detailed, "
        "professional photography, natural lighting, sharp focus, "
        "DSLR, canon EOS R5, 85mm lens, shallow depth of field"
    ),
    "二次元": (
        "anime style, manga art, studio ghibli inspired, "
        "vibrant colors, clean lines, cel shading, "
        "makoto shinkai aesthetic, beautiful sky, detailed background"
    ),
    "油画": (
        "oil painting, classic oil on canvas, textured brushstrokes, "
        "Rembrandt lighting, rich color palette, impressionist style, "
        "fine art, gallery quality, chiaroscuro, masterpiece"
    ),
    "赛博朋克": (
        "cyberpunk, neon lights, futuristic city, rain-slicked streets, "
        "blade runner aesthetic, dystopian atmosphere, high tech low life, "
        "vibrant neon colors, dark moody atmosphere, volumetric lighting"
    ),
}

# 比例选项
ASPECT_RATIOS = {
    "1:1（正方形）": "1:1",
    "16:9（宽屏）": "16:9",
    "9:16（竖屏）": "9:16",
    "4:3（标准）": "4:3",
    "3:4（竖版标准）": "3:4",
}

STYLE_LABELS = list(STYLE_SUFFIXES.keys())
