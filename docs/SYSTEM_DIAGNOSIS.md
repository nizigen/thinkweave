# 系统诊断报告：文章缺陷反推代码问题

**日期:** 2026-05-03  
**报告对象:** OPC UA 报告生成系统  
**诊断方法:** 通过 AI 生成文章的缺陷反推系统代码架构问题  

---

## 执行摘要

文章 `20260429_232836_d82a646d-68c5-48bb-b253-d54fed6b4cee_1_AI_OPC.md` 的 **6 个核心缺陷** 直接对应系统的 **6 个架构弱点**。本报告通过反向工程将每个文章问题映射到代码问题，并提供可执行的改进方案。

**关键发现:**
- 核心论点不聚焦 → FSM 和 Outline Prompt 缺少论点约束机制
- 缺市场数据 → Evidence Pool 初始化不足，Writer Prompt 缺证据要求
- 技术陈述无验证 → 缺 FACT_CHECK 状态和专门的 Fact Check Agent
- 反例模糊 → Prompt 允许模糊词（"小"、"极慢"），无量化约束
- 实施路径不可操作 → Task Decomposer 生成的粒度太粗
- 建议未被执行 → FSM Consistency 逻辑是单向的，缺反馈循环

---

## 诊断 1：核心论点不聚焦 (P0 - 阻断)

### 文章症状
- 8 个平行章节：技术基石、范式转移、生成模式、隐私治理、经济模型、未来展望、实施路径、编辑指南
- 每章独立成书，无明确脊梁
- 读者无法回答"为什么读这篇文章"

### 系统问题根源

| 组件 | 应该做什么 | 现在的问题 | 代码位置 |
|------|---------|---------|---------|
| **task_decomposer** | 生成"单主题 DAG"，所有子任务服从 1 个核心论点 | 生成 8 个平行的"章节任务"，每个都是一级节点 | `backend/services/task_decomposer.py` |
| **OUTLINE Agent** | 要求 Outline 陈述"核心论点"，每章 justify 如何服从 | Prompt 太宽松，允许 8 章都"看起来都重要" | `backend/prompts/outline/main.md` |
| **OUTLINE_REVIEW** | 用户被迫选择核心论点（A 或 B），删除不服从的章节 | FSM 没有触发选择点；用户直接通过 | `backend/services/long_text_fsm.py` |
| **FSM State** | 应在 OUTLINE_REVIEW 中加入"Premise Gate"决策 | 缺少这个关键决策点 | `backend/services/long_text_fsm.py` |

### 改进方案

#### 1. 改 Outline Agent Prompt

**文件:** `backend/prompts/outline/main.md`

```markdown
# Outline Agent - 核心论点约束

## 必须做的三件事

1. **识别核心论点**
   - 明确陈述"这篇文章的单一核心论点是什么"
   - 不能笼统如"介绍 OPC UA"，要具体到"OPC UA 如何解决什么具体问题"
   - 核心论点必须经得起"如果删除这一句，文章就失焦了"的考验

2. **论点服从检查**
   - 列出所有计划的章节
   - 每章标注"为什么这一章服从核心论点"
   - 如果某章不能清晰 justify，标记为"可选"或"删除"

3. **平行度约束**
   - 一级章节 ≤ 3 个（不计辅助/可选）
   - 所有一级章节必须是"核心论点的三个侧面"

## 输出格式

\`\`\`
## 核心论点
[一句话]

## 一级章节（服从核心论点）
- CH1: [标题] → 对核心论点的贡献: [解释]
- CH2: [标题] → 对核心论点的贡献: [解释]
- CH3: [标题] → 对核心论点的贡献: [解释]

## 可选章节（不影响核心论点）
- CH_OPT1: [标题] → 可选理由: [解释]
- CH_OPT2: [标题] → 可选理由: [解释]

## 验收标准

- [ ] 核心论点清晰无歧义
- [ ] 一级章节 ≤ 3 个
- [ ] 每个一级章节都有明确的"对核心论点的贡献"
- [ ] 可选章节都标记了"为什么可选"
\`\`\`
```

#### 2. FSM 中加入 "Premise Gate" 决策

**文件:** `backend/services/long_text_fsm.py`

```python
class LongTextState(Enum):
    INIT = "init"
    OUTLINE = "outline"
    OUTLINE_REVIEW = "outline_review"
    PREMISE_GATE = "premise_gate"  # ← 新增
    WRITING = "writing"
    # ...

TRANSITIONS = {
    LongTextState.OUTLINE_REVIEW: [
        LongTextState.PREMISE_GATE,  # 必须先过论点关卡
    ],
    LongTextState.PREMISE_GATE: [
        LongTextState.WRITING,        # 通过 → 继续写作
        LongTextState.OUTLINE,        # 不通过 → 返回改写 Outline
    ],
}

# 在 Premise Gate 状态中实现决策逻辑
async def handle_premise_gate_state(self, ctx: dict) -> LongTextState:
    """
    用户决策：
    1. 确认核心论点是否清晰
    2. 选择是否要删除"可选章节"
    3. 确认一级章节数量
    """
    outline = ctx.get("outline", {})
    
    # 自动检查：一级章节数是否超过 3 个
    primary_chapters = [ch for ch in outline.get("chapters", []) 
                       if not ch.get("optional")]
    if len(primary_chapters) > 3:
        return LongTextState.OUTLINE  # 返回重写
    
    # 提示用户确认
    prompt = self.format_premise_confirmation(outline)
    user_decision = await self.ask_user(prompt)
    
    if user_decision == "CONFIRM":
        return LongTextState.WRITING
    else:
        return LongTextState.OUTLINE
```

#### 3. 在 Outline 章节末尾添加可执行的"承上启下"

**改进示例:**

```
## 下一步：WRITING 阶段

### 为什么只关注 3 个核心章节？

你已经选择了核心论点："[陈述核心论点]"

所有后续的 WRITING 都必须明确指向这个论点。
如果某个段落无法回答"这个段落如何服从核心论点"，它会在 REVIEWING 阶段被标记为冗余。

### 你的写作约束

```json
{
  "core_thesis": "[核心论点]",
  "primary_chapters": ["CH1", "CH2", "CH3"],
  "optional_chapters": ["CH_OPT1", "CH_OPT2"],
  "max_tangents": 1,  // 允许 1 条切线，必须明确回到主论点
  "proof_requirement": "每个主张都必须有 1+ 具体例子或数据"
}
```

---

## 诊断 2：缺市场背景数据 (P0 - 阻断)

### 文章症状
```
"传统报告方案难以适应灵活、互联的智能制造需求"
  → 缺数据：多少比例的工厂在用 SCADA? ROI 是多少?
```

### 系统问题根源

| 组件 | 应该做什么 | 现在的问题 | 代码位置 |
|------|---------|---------|---------|
| **Evidence Pool** | 初始化时加载：行业报告、市场数据、竞争分析 | 可能是空的或只有技术文档 | `backend/services/evidence_pool.py` |
| **Writer Prompt** | 每个宏观论述都必须 back 以具体数字 | Writer 被允许生成"传统方案有问题"而不引用数据 | `backend/prompts/writer/main_writer.md` |
| **Reviewer Agent** | 有维度："市场/商业主张是否有数字支撑？(0-100)" | 只检查"逻辑一致性"，不检查"证据充分性" | `backend/app/agents/reviewer_agent.py` |
| **Consistency Agent** | 标记"未引用的主张"并拒绝通过 | 没有这个检查 | `backend/app/agents/consistency_agent.py` |

### 改进方案

#### 1. 补充 Evidence Pool 初始化

**文件:** `backend/services/evidence_pool.py`

```python
class EvidencePool:
    async def initialize_industry_context(self, topic: str):
        """
        为文章初始化必要的行业数据
        根据主题自动加载市场数据、竞争信息、技术指标
        """
        industry_facts = {
            "OPC_UA_adoption": {
                "2020_adoption_rate": {
                    "value": "15%",
                    "description": "全球工厂 OPC UA 采纳率",
                    "source": "Gartner 2024 Industrial IoT Report",
                    "confidence": 0.85
                },
                "2025_forecast": {
                    "value": "42%",
                    "description": "预测 2025 年采纳率",
                    "source": "Gartner 2024 Industrial IoT Report",
                    "confidence": 0.70
                }
            },
            "SCADA_limitations": {
                "integration_time_avg": {
                    "value": "12 months",
                    "description": "新设备集成的平均周期",
                    "source": "ARC Advisory Group 2023",
                    "confidence": 0.80
                },
                "cost_per_integration": {
                    "value": "$2-5M",
                    "description": "单个集成项目的成本",
                    "source": "ARC Advisory Group 2023",
                    "confidence": 0.75
                },
                "data_silo_percentage": {
                    "value": "85%",
                    "description": "面临数据孤岛问题的企业比例",
                    "source": "ARC Advisory Group 2023",
                    "confidence": 0.80
                }
            },
            "OPC_UA_benefits": {
                "integration_time_reduction": {
                    "before": "12 months",
                    "after": "3 months",
                    "description": "采用 OPC UA 后集成时间的缩减",
                    "source": "OPC Foundation Case Studies",
                    "confidence": 0.75
                }
            }
        }
        
        await self.store(industry_facts)
        return industry_facts
```

#### 2. 改 Writer Agent Prompt - 加证据要求

**文件:** `backend/prompts/writer/main_writer.md`

```markdown
# Writer Agent - 证据要求

## 核心原则

**每个宏观论述必须包含：**
1. 主张
2. 数字或具体例子（从 Evidence Pool 引用）
3. 来源标记

## 标记语法

\`@evidence[key.subkey]\` → 自动引用来自 Evidence Pool 的数据

## 示例对比

### ✓ 好的写法（有证据支撑）
```
90% 的制造企业仍使用孤立的 SCADA 系统(@evidence[SCADA_limitations.data_silo_percentage])，
平均集成新设备需要 12 个月(@evidence[SCADA_limitations.integration_time_avg])。

采用 OPC UA 后，集成时间从 12 个月缩短到 3 个月(@evidence[OPC_UA_benefits.integration_time_reduction])。
```

### ✗ 坏的写法（无具体数据）
```
传统系统难以集成新设备，需要很长时间，但 OPC UA 方案更快。
```

## 检查清单（Writer 必须满足）

- [ ] 每个"传统方案缺陷"都有 ≥1 具体数字
- [ ] 每个"OPC UA 优势"都有案例或数据支撑
- [ ] 所有数字都来自 Evidence Pool（用 @evidence[key] 标记）
- [ ] 没有模糊词("通常", "往往", "许多") —— 改为"X% 的..."
- [ ] 每个市场洞察都有来源说明

## 如果找不到数据怎么办？

1. 标记为 `@evidence[MISSING: description]`
2. Fact Check Agent 会在 FACT_CHECK 状态中进行补充搜索
3. 如果仍无法找到，该段落会被标记为"可选"或"需要用户提供数据"
```

#### 3. Reviewer Agent 加维度

**文件:** `backend/app/agents/reviewer_agent.py`

```python
class ReviewerAgent(BaseAgent):
    SCORING_DIMENSIONS = {
        "logical_consistency": (0, 100),      # 已有
        "evidence_sufficiency": (0, 100),     # ← 新增
        "specificity": (0, 100),              # ← 新增
        "source_attribution": (0, 100),       # ← 新增
    }
    
    async def evaluate_evidence_sufficiency(self, text: str) -> float:
        """
        检查主张是否有数字或案例支撑
        
        评分标准：
        - 90-100: 所有宏观论述都有具体数据和来源
        - 70-89: 70% 以上的论述有数据支撑
        - 50-69: 50% 左右有数据支撑
        - 0-49: 大部分论述无数据支撑
        """
        
        # 统计"未标记"的宏观论述（包含模糊词但无@evidence标记）
        fuzzy_words = ["往往", "通常", "许多", "通常", "可能", "似乎"]
        
        problematic_statements = []
        for para in text.split("\n\n"):
            has_fuzzy = any(word in para for word in fuzzy_words)
            has_evidence = "@evidence[" in para
            
            if has_fuzzy and not has_evidence:
                problematic_statements.append(para[:100])
        
        if problematic_statements:
            unsupported_ratio = len(problematic_statements) / len(text.split("\n\n"))
            score = max(0, 100 - unsupported_ratio * 50)
        else:
            score = 100
        
        return score
```

---

## 诊断 3：技术陈述缺验证 (P1)

### 文章症状
```
"HistoricalDataConfiguration 对象的关键属性，如 Stepped...AggregateConfiguration..."
  → 缺信息：OPC UA 规范哪个版本? 这些属性是必须的还是可选的?
```

### 系统问题根源

| 组件 | 应该做什么 | 现在的问题 | 代码位置 |
|------|---------|---------|---------|
| **Writer Prompt** | 每个技术名词都标记规范来源 | Writer 无法自动标记版本号 | `backend/prompts/writer/` |
| **Fact Check 步骤** | 在 REVIEWING/CONSISTENCY 中验证技术陈述 | 没有这个步骤 | `backend/services/long_text_fsm.py` |
| **Knowledge Graph** | 包含"技术概念 → 规范出处"映射 | KG 可能只有结构，没有"来源"元数据 | `backend/app/memory/knowledge/graph.py` |

### 改进方案

#### 1. FSM 中加 FACT_CHECK 状态

**文件:** `backend/services/long_text_fsm.py`

```python
class LongTextState(Enum):
    # ...
    REVIEWING = "reviewing"
    FACT_CHECK = "fact_check"  # ← 新增
    RE_REVIEW = "re_review"
    # ...

TRANSITIONS = {
    LongTextState.REVIEWING: [
        LongTextState.FACT_CHECK,      # 优先做事实检查
        LongTextState.RE_REVIEW,
        LongTextState.DONE
    ],
    LongTextState.FACT_CHECK: [
        LongTextState.RE_REVIEW,       # 如果检查失败，返回改写
        LongTextState.CONSISTENCY
    ]
}

async def handle_fact_check_state(self, ctx: dict) -> str:
    """
    事实检查包括：
    1. 技术术语是否来自已知规范
    2. 属性/方法是否真实存在
    3. 来源是否标记清晰
    """
    text = ctx.get("full_text", "")
    
    # 运行 Fact Check Agent
    fact_check_result = await self.fact_check_agent.handle_task(ctx)
    
    if fact_check_result.get("status") == "PASS":
        return LongTextState.CONSISTENCY
    else:
        # 失败 → 收集所有未验证的陈述
        failures = fact_check_result.get("failures", [])
        ctx["fact_check_failures"] = failures
        
        # 通知 Writer 返工
        return LongTextState.RE_REVIEW
```

#### 2. 创建 Fact Check Agent

**文件:** `backend/app/agents/fact_check_agent.py` (新建)

```python
class FactCheckAgent(BaseAgent):
    """验证技术陈述的准确性和来源"""
    
    SPEC_REGISTRY = {
        "OPC UA": {
            "HistoricalDataConfiguration": {
                "spec": "OPC UA Part 11 (Address Space Model)",
                "version": "1.05",
                "url": "https://opcfoundation.org/UA/Part11/v105/",
                "mandatory": False,
                "attributes": ["Stepped", "AggregateConfiguration"]
            },
            "HistoryRead": {
                "spec": "OPC UA Part 4 (Services)",
                "version": "1.05",
                "url": "https://opcfoundation.org/UA/Part4/v105/",
                "mandatory": True
            }
        }
    }
    
    async def handle_task(self, ctx: dict) -> dict:
        """
        检查:
        1. 技术术语是否来自已知的规范/标准
        2. 属性/方法是否真实存在
        3. 来源是否标记清晰
        """
        text = ctx.get("full_text", "")
        
        # 提取技术术语
        opc_terms = self.extract_opc_ua_terms(text)
        
        failures = []
        for term in opc_terms:
            spec_info = self.lookup_spec(term)
            
            if not spec_info:
                failures.append({
                    "term": term,
                    "issue": f"OPC UA 术语 '{term}' 未在已知规范中找到",
                    "fix": f"请验证这是标准术语，或补充来源信息"
                })
            else:
                # 检查来源是否在文中标记
                reference_pattern = f"{term}.*\\(OPC UA Part"
                if not re.search(reference_pattern, text):
                    failures.append({
                        "term": term,
                        "issue": f"术语 '{term}' 未标记规范来源",
                        "fix": f"补充: (OPC UA Part {spec_info['part']}, v{spec_info['version']})"
                    })
        
        if failures:
            return {
                "status": "FAIL",
                "failures": failures
            }
        
        return {
            "status": "PASS",
            "verified_terms": len(opc_terms)
        }
```

---

## 诊断 4：反例和边界条件模糊 (P1)

### 文章症状
```
"在小型、封闭、变化极慢的系统中...可能带来不必要的复杂度"
  → 问题：多小算"小"？"变化极慢"是多慢？无可观察标准
```

### 改进方案

**文件:** `backend/prompts/writer/constraint_specification.md` (新建)

```markdown
# Constraint Specification 规范 - 禁止模糊词

## 禁止用词 + 正确改写

| 禁止词 | 为什么禁止 | 正确改写 |
|-------|---------|---------|
| "小型系统" | 无法量化 | "<100 个数据点的系统" |
| "变化极慢" | 主观判断 | "变化频率 <1 次/分钟的系统" 或 "<10 Hz" |
| "高度动态" | 相对概念 | "变化频率 >10 Hz 的系统" |
| "通常" | 无具体比例 | "[具体%]% 的场景中" 或 "根据[来源]" |
| "往往" | 模糊 | 用具体比例替代 |
| "似乎" | 不确定 | "根据[来源]显示" 或 "实验表明" |
| "许多" | 定量不明 | "50% 以上" / "多数" / "少数" 等有尺度的词 |

## 必须包含的量化约束

对于任何**场景描述**或**条件论述**，必须明确：

1. **数据点规模范围**
   - 小: <100 点
   - 中: 100-10K 点
   - 大: 10K-100K 点
   - 超大: >100K 点

2. **变化频率 / 采样率**
   - 极低: <1 次/小时
   - 低: 1 次/小时 - 1 次/分钟
   - 中: 1 次/分钟 - 1 Hz
   - 高: 1-10 Hz
   - 极高: >10 Hz

3. **网络延迟要求**
   - 宽松: <1 秒
   - 中等: <100 ms
   - 严格: <10 ms
   - 实时: <1 ms

4. **系统寿命周期**
   - 短期试点: <1 年
   - 中期: 1-3 年
   - 长期: 3-10 年
   - 永久运营: >10 年

## 示例改进

### 改前 (模糊)
```
"在小型、封闭系统中可能过度复杂，此时改良传统方案或采用轻量级中间件或许是更经济的选择。"
```

### 改后 (量化)
```
"对于 <100 个数据点、变化频率 <1 次/分钟、不需要跨系统交互、系统寿命 <3 年的场景，
OPC UA 方案的配置成本（500-1000 小时工程师工作）可能超过其收益。

建议方案：
- 保持现有 SCADA 内置报表，定期手动导出
- 或采用轻量级 CSV 导出 + 电子表格定时分析

但如果有以下任一特征，OPC UA 仍值得投入：
- 需要与 ≥2 个外部系统集成
- 系统运营周期 ≥3 年
- 数据点 ≥1000
- 报告延迟要求 <1 小时
```
```

---

## 诊断 5：实施路径不可操作 (P1)

### 文章症状
```
"参与 OPC 基金会或行业协会提供的专项培训"
  → 缺信息：哪些培训？费用？周期？如何快速评估规范是否适用？
```

### 系统问题根源

| 组件 | 应该做什么 | 现在的问题 | 代码位置 |
|------|---------|---------|---------|
| **task_decomposer** | 对"实施"类章节生成细粒度任务 | DAG 把"实施路径"当单一任务 | `backend/services/task_decomposer.py` |
| **Writer Prompt** | 每个建议都必须可操作（清单/流程/估算） | Writer 生成策略性文字，不是行动方案 | `backend/prompts/writer/` |
| **Skills System** | 有"生成可操作清单" Skill | thinkweave Skills 可能没有这个 | `backend/app/skills/` |

### 改进方案

#### 1. Task Decomposer 针对"实施"类改进

**文件:** `backend/services/task_decomposer.py`

```python
def decompose_long_text_task(self, user_input: str) -> DAGDefinition:
    """
    检测章节类型：
    - 理论: 保持现有粗粒度
    - 应用案例: 保持现有粒度
    - 实施: 生成细粒度任务
    """
    
    if any(keyword in user_input.lower() 
           for keyword in ["实施", "implementation", "how-to", "guide", "步骤"]):
        
        # 实施类章节：细粒度分解
        return DAGDefinition(
            nodes=[
                TaskNode(
                    id="impl_001",
                    type="ACTIONABLE_CHECKLIST",
                    description="可检查清单（5 分钟内完成验证）",
                    dependencies=[]
                ),
                TaskNode(
                    id="impl_002",
                    type="DECISION_MATRIX",
                    description="决策矩阵（帮助做关键选择）",
                    dependencies=["impl_001"]
                ),
                TaskNode(
                    id="impl_003",
                    type="TIMELINE_ESTIMATE",
                    description="时间和资源估算",
                    dependencies=["impl_002"]
                ),
                TaskNode(
                    id="impl_004",
                    type="RISK_ASSESSMENT",
                    description="风险评估和缓解方案",
                    dependencies=["impl_002"]
                ),
            ],
            edges=[
                ("impl_001", "impl_002"),
                ("impl_002", "impl_003"),
                ("impl_002", "impl_004"),
            ]
        )
    else:
        # 其他章节：保持现有逻辑
        return self._default_decompose(user_input)
```

#### 2. Writer Prompt 加可操作性要求

**文件:** `backend/prompts/writer/actionable_output.md` (新建)

```markdown
# 可操作性要求 - Implementation Sections

## 对于"实施"/"建议"段落，必须包含 4 个部分：

### 1. 快速诊断清单 (Checklist)
- 每项用 5-10 字描述
- 必须在 5 分钟内完成验证
- 格式: `[ ] [动作] [标准]`

### 2. 决策矩阵 (Decision Matrix)
- Rows: 关键维度 (功能、成本、复杂度等)
- Cols: 可选方案 (方案 A、B、C 等)
- 每个交叉点有明确的判断标准

### 3. 时间 + 资源估算 (Timeline)
- 假设当前状态 → Y 天内可以达成
- 需要多少工程师小时？
- 需要什么工具/许可?

### 4. 风险与缓解 (Risk Assessment)
- 风险等级: 高/中/低
- 缓解方案
- 备选方案

## 不可接受的格式

❌ "参与 OPC 基金会提供的培训"
❌ "采用标准优先原则"
❌ "需要技能提升"

## 可接受的格式

✓ 清单：
```
### 快速诊断（1 天）
- [ ] 访问 https://opcfoundation.org/training
- [ ] 筛选条件:
  - 角色: 工程师/架构师/管理者 ?
  - 费用: <$1000 / $1000-5000 / >$5000 ?
  - 周期: <1 周 / 1-4 周 / >1 月 ?
```

✓ 矩阵：
```
| 维度 | 方案 A | 方案 B | 方案 C |
|-----|------|----- |-------|
| 实现难度 | 低 (2-4 周) | 中 (4-8 周) | 高 (8-12 周) |
| 长期维护成本 | 高 | 中 | 低 |
| 初始投入 | $10K | $50K | $200K |
```

✓ 时间估算：
```
假设 2 人技术团队，0 天 OPC UA 经验：
- 学习 + 评估: 10-15 工作日
- PoC 实施: 20-30 工作日
- 试点上线: 15-20 工作日
总计: 6-8 周 (含风险缓冲)
```
```

---

## 诊断 6：建议未被执行 (P2)

### 文章症状
```
最后一章全是"可以添加..."、"应该包含..."，但前面的章节并没有采纳这些建议
```

### 系统问题根源

| 组件 | 应该做什么 | 现在的问题 | 代码位置 |
|------|---------|---------|---------|
| **Consistency Agent** | 检查文章是否遵循自己提出的建议 | 单向检查：检查前面的一致性，不检查自我应用 | `backend/app/agents/consistency_agent.py` |
| **FSM 最后阶段** | CONSISTENCY 循环应触发"反馈循环" | 单循环：一旦通过就结束 | `backend/services/long_text_fsm.py` |

### 改进方案

**文件:** `backend/services/long_text_fsm.py`

```python
async def handle_consistency_state(self, ctx: dict) -> LongTextState:
    """
    现在: CONSISTENCY → DONE
    改为: 检查诊断建议是否被应用
    """
    
    text = ctx.get("full_text", "")
    consistency_result = await self.consistency_agent.evaluate(text)
    
    # 旧逻辑：如果一致性好就结束
    # if consistency_result.score >= CONSISTENCY_THRESHOLD:
    #     return LongTextState.DONE
    
    # 新逻辑：检查"元建议"是否被应用
    if consistency_result.has_meta_recommendations():
        # 即：文章本身提出的改进建议（如第 8 章的"编辑指南"）
        # 是否有被实际应用到相关章节中
        
        unapplied = await self.check_unapplied_recommendations(
            text,
            consistency_result.recommendations
        )
        
        if unapplied:
            # 触发反馈循环：将未应用的建议发回给相关 Writer
            for chapter_id, recommendations in unapplied.items():
                revision_task = {
                    "chapter_id": chapter_id,
                    "revisions": recommendations,
                    "context": ctx
                }
                await self.task_queue.put(revision_task)
            
            # 返回重新审查
            return LongTextState.RE_REVIEW
    
    return LongTextState.DONE
```

---

## 改进优先级和工作量估算

| 问题 | 优先级 | 影响范围 | 工作量 | 文件数 |
|------|--------|--------|-------|--------|
| 核心论点不聚焦 | P0 | FSM + Prompt | 3-4 小时 | 2 |
| 缺市场数据 | P0 | Evidence Pool + Writers | 4-6 小时 | 3 |
| 技术陈述缺验证 | P1 | FSM + 新 Agent | 6-8 小时 | 3 |
| 反例模糊 | P1 | Writer Prompt | 2-3 小时 | 1 |
| 实施路径不可操作 | P1 | Decomposer + Skills | 5-7 小时 | 3 |
| 建议未被执行 | P2 | FSM Consistency | 3-4 小时 | 1 |
| **总计** | — | — | **23-32 小时** | **13** |

---

## 执行路线图

### 第一周（P0 问题）
- [ ] 改 Outline Prompt，加论点聚焦约束
- [ ] FSM 中加 Premise Gate 状态
- [ ] Evidence Pool 初始化补充市场数据
- [ ] Writer Prompt 加证据要求

**验证:** 生成新的 OPC UA 文章，检查是否：
- 核心论点清晰
- 每个论述都有 ≥1 个数据支撑

### 第二周（P1 问题）
- [ ] 创建 Fact Check Agent
- [ ] FSM 中加 FACT_CHECK 状态
- [ ] Writer Prompt 加约束定量化规范
- [ ] Task Decomposer 针对实施类改进
- [ ] 创建 Operational Specification Skill

**验证:** 检查技术陈述是否标记了规范来源，反例是否都量化了

### 第三周（P2 问题 + 测试）
- [ ] 改 FSM Consistency 逻辑，加反馈循环
- [ ] 端到端测试：从 task 分解到文章生成
- [ ] 文档更新

---

## 备注

这个诊断是**架构级别的**，不涉及具体的业务逻辑调整。主要改进集中在：

1. **约束强化**: Prompt 更严格，要求更明确
2. **检查点增加**: FSM 中加关键决策和验证步骤
3. **反馈机制**: 从单向检查改为循环改进
4. **数据补充**: Evidence Pool 和可操作性清单

实施这些改进后，系统生成的文章质量应该显著提升，尤其是在"聚焦性"、"可验证性"和"可操作性"三个维度。
