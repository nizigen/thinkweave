---
name: awesome-ai-research-writing
description: "学术论文写作 prompt 工具集，包含 16 个子技能。覆盖中英翻译、学术润色、文本缩扩写、逻辑检查、去AI味、论文架构图、图表标题生成、实验分析、审稿视角审视、模型选择等场景。适用于 ICML/ICLR/NeurIPS/ACL 等顶会论文写作。"
---

# Awesome AI Research Writing

学术论文写作 prompt 工具集，来自 [Leey21/awesome-ai-research-writing](https://github.com/Leey21/awesome-ai-research-writing)。

调研了 MSRA、Seed、SH AI Lab 等顶尖研究机构的研究员，以及北大、中科大、上交的硕博同学，将他们日常使用的写作技巧开源。

## Skills (16)

### 翻译与改写
| Skill | Purpose |
|-------|---------|
| cn-to-en | 中文草稿翻译为英文 LaTeX 论文片段 |
| en-to-cn | 英文 LaTeX 翻译为流畅中文文本 |
| cn-polish | 中文草稿重写为学术规范的中文论文段落（Word 适配） |
| compress | 微幅缩减英文 LaTeX 字数（5-15 词），保留全部信息 |
| expand | 微幅扩写英文 LaTeX（5-15 词），深挖隐含逻辑 |

### 润色与检查
| Skill | Purpose |
|-------|---------|
| polish-en-paper | 英文论文深度润色，达到顶会出版水准 |
| polish-cn-paper | 中文论文润色，克制修改原则 |
| logic-check | 终稿逻辑检查，高容忍度红线审查 |
| deai-en-latex | 去 AI 味（英文 LaTeX），重写为自然学术表达 |
| deai-cn-word | 去 AI 味（中文 Word），去翻译腔与机械感 |

### 图表与分析
| Skill | Purpose |
|-------|---------|
| paper-architecture-diagram | 论文架构图设计（扁平矢量风格） |
| figure-caption | 生成符合顶会规范的英文图标题 |
| table-caption | 生成符合顶会规范的英文表标题 |
| experiment-analysis | 实验数据分析，生成 LaTeX 分析段落 |

### 审视与参考
| Skill | Purpose |
|-------|---------|
| reviewer-perspective | 以 Reviewer 视角审视论文，模拟审稿报告 |
| model-selection | 学术写作场景下的 AI 模型选择参考 |

## 互补说明

- `humanizer-zh` 已安装 -- 与去 AI 味 prompt 互补（后者更细分 LaTeX/Word 场景）
- `AI-Research-SKILLs/20-ml-paper-writing` 已安装 -- 覆盖论文结构，不与翻译/润色重叠

## 原始 Prompt 归档

所有原始 prompt 保存在 `prompts/` 目录，可手动导入 prompt-tools.exe。
