# Jay-AI-Tools — 多功能 AI 工作台

基于 Streamlit + MiniMax M3 的一站式 AI 工具集，涵盖科研、写作、数学、视觉、音乐、游戏六大模块。已开源到github，链接为 https://github.com/Jaysforever/minimax-agent

## 🚀 快速启动

```bash
# 1. 激活虚拟环境
conda activate agent

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 MiniMax API Key

# 4. 启动
streamlit run app.py
```

Windows 用户也可直接双击 `start.bat` 启动。

## 📦 功能模块

### 🔬 科研助手

| 子功能 | 说明 |
|--------|------|
| 论文阅读 | 上传多个 PDF → 一键分析（总结/贡献/方法/实验）→ 多轮问答 |
| 文献搜索 | 关键词搜索 → Semantic Scholar / arXiv 双源 → AI 分类总结 → 生成研究报告 |
| 每日精读 | 自动从 6 个热门方向推荐高价值论文 → AI 精讲 → PDF 嵌入预览 → 边看边问 |

### ✍️ 写作助手

- 6 种题材：小红书风格 / 正式公文 / 科技博文 / 现代诗 / 古诗词 / 微小说
- 创意题材可调 Temperature，实用文体默认严谨模式
- 内置 AI 朗读：10 种音色、语速可调、支持语气词标签
- 导出为 txt 文件

### 🧮 数学解题

- **文本输入**：直接输入数学问题
- **语音录入**：Whisper 本地语音转文字（需安装 ffmpeg + PyTorch）
- **图片输入**：支持多张图片上传（题目截图、手写算式、几何图形）
- M3 多模态 API 直接理解图片内容
- 思维链推理 + LaTeX 公式渲染（`st.markdown` + `st.latex` 双重渲染）
- 多轮对话，支持追问

### 🎨 AI生图

- 上传参考图（可选）→ 输入中文描述 → AI 增强英文 Prompt（可编辑）→ 生成图片
- i2i 智能回退：有参考图时自动尝试主体保留，失败回退纯文本
- 历史画廊：多版本对比、切换
- 对话修图：多轮自然语言修改（"改成夜晚"、"换成油画风"）

### 🎵 音乐创作

**歌词创作模式：**
- AI 生成歌词（官方 lyrics_generation API）→ 可编辑 → 生成音乐

**翻唱模式：**
- 上传音频 → 选时间段 → 截断 → 分析歌曲结构 → 写新歌词 → 生成翻唱
- 保留原曲音色，替换歌词内容

### 🎮 游戏创作

- **6 个快捷模板**：贪吃蛇 / 俄罗斯方块 / 打砖块 / 飞镖 / 赛车 / 翻牌
- **实时流式生成**：`st.write_stream()` 逐字推送代码，看着代码被「写」出来
- **对话式创作**：描述需求 → AI 生成完整 HTML+JS 游戏 → 弹窗全屏预览运行
- **多轮修改**：直接说「把蛇改成蓝色」 → 立即生成新版本
- **全屏预览弹窗**：CSS 强制 95vw × 90vh，代码块全宽显示
- **下载独立 HTML**：保存到本地直接打开玩

## 🏗️ 项目结构

```
agent/
├── app.py                      # 主入口（侧边栏路由）
├── core/
│   └── model.py                # MiniMax API 封装（chat + multimodal_chat）
├── tools/                      # 功能模块
│   ├── research_assistant.py   # 科研助手
│   ├── writer.py               # 写作助手（含朗读）
│   ├── math_solver.py          # 数学解题
│   ├── image_generator.py      # AI 视觉创作
│   ├── music_generator.py      # 音乐创作
│   ├── game_creator.py         # 游戏创作（实时流式 + 全屏预览）
│   └── audio_processor.py      # Whisper STT
├── prompts/                    # 提示词管理
│   ├── research.py / writer.py / math.py / image.py / music.py / game.py
├── .env                        # API Key 配置
├── requirements.txt            # Python 依赖
├── start.bat                   # Windows 一键启动
```

## 🔑 API 配置

在 `.env` 文件中填入：

```
MINIMAX_API_KEY=你的API密钥
```

支持的 MiniMax API：

| API | 用途 |
|-----|------|
| Chat Completions (`chatcompletion_v2`) | 文本对话、多模态理解 |
| Image Generation (`image_generation`) | 文生图、图生图 |
| Music Generation (`music_generation`) | 音乐生成、翻唱 |
| Lyrics Generation (`lyrics_generation`) | 歌词生成 |
| T2A (`t2a_v2`) | 文字转语音 |

## 📋 依赖

- Python 3.10+
- Streamlit >= 1.28.0
- requests, python-dotenv, pypdf, pydub
- openai-whisper（语音转文字，可选）
- streamlit-mic-recorder（麦克风录音，可选）
- ffmpeg（音频处理，系统级依赖）

## 📝 开发规范

- 模块隔离：新增功能在 `tools/` 下新建文件，在 `app.py` 注册
- 提示词管理：`prompts/` 下的 `PROMPTS_DICT` 统一管理，禁止硬编码
- 状态管理：使用 `st.session_state` 保持多轮对话上下文
- **流式输出**：长内容生成统一用 `st.write_stream()`，避免 spinner 卡顿错觉
