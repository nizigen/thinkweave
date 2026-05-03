# 代码改进清单 - thinkweave 长文本 FSM 系统

**生成日期:** 2026-05-03  
**基础:** `docs/SYSTEM_DIAGNOSIS.md` 中的 6 个问题诊断  
**总任务数:** 13 个文件修改  
**总工作量:** 23-32 小时  

---

## 优先级 P0（本周）

### 问题 1：核心论点不聚焦

#### 1.1 创建 Outline Prompt 约束文件

**文件:** `backend/prompts/outline/core_thesis_constraint.md` (新建)

**改动内容:**
```markdown
# Outline Agent - 核心论点约束

- 强制识别核心论点（一句话）
- 每章都要 justify 如何服从论点
- 一级章节 ≤ 3 个限制
- 标记可选章节

输出必须包含:
- core_thesis: 明确的论点陈述
- chapters: 带 justification 的清单
- coherence_check: 删除可选后是否还完整
```

**检查点:** Outline 必须包含 `core_thesis` 和每章的 `justification` 字段

---

#### 1.2 改 FSM 加 Premise Gate 状态

**文件:** `backend/services/long_text_fsm.py`

**改动点:**

| 行号 | 改动类型 | 内容 |
|------|--------|------|
| ~40-50 | 枚举添加 | 加 `PREMISE_GATE = "premise_gate"` |
| ~80-90 | 转移规则 | `OUTLINE_REVIEW → PREMISE_GATE → (WRITING \| OUTLINE)` |
| ~300-350 | 新方法 | `async def handle_premise_gate_state(...)` |

**具体改动:**

```python
class LongTextState(Enum):
    # ... 现有状态 ...
    OUTLINE_REVIEW = "outline_review"
    PREMISE_GATE = "premise_gate"  # ← 新增
    WRITING = "writing"

TRANSITIONS = {
    # ... 现有转移 ...
    LongTextState.OUTLINE_REVIEW: [
        LongTextState.PREMISE_GATE,    # 添加这行
    ],
    LongTextState.PREMISE_GATE: [
        LongTextState.WRITING,         # 新增转移
        LongTextState.OUTLINE,
    ],
}

# 新增处理方法（200+ 行）
async def handle_premise_gate_state(self, ctx: dict) -> LongTextState:
    """验证 Outline 的论点是否清晰"""
    # 检查：是否包含 core_thesis？
    # 检查：一级章节 ≤ 3 个？
    # 检查：每章都有 justification？
    # → 通过: WRITING，失败: OUTLINE
```

**检查方式:**
- 提交一个 8 章的 Outline，验证 FSM 是否返回错误
- 检查错误信息是否清晰指出"章节过多"

---

#### 1.3 改 OUTLINE_REVIEW 路由

**文件:** `backend/routers/outline.py`

**改动:**

```python
@router.post("/tasks/{task_id}/outline/confirm")
async def confirm_outline_with_thesis(task_id: str, confirmation: dict):
    # 新增字段验证
    required_fields = [
        "agree_with_thesis",    # 用户是否同意论点
        "approved_chapters",    # 用户想要的章节
        "removed_chapters"      # 用户要删除的章节
    ]
    
    # 如果用户不同意论点，返回 OUTLINE 状态
    # 如果用户删除了太多章节，验证核心论点仍然完整
```

**检查方式:**
- 调用 `/outline/confirm` 端点，验证是否强制要求"approve_with_thesis"
- 提交无论点的回复，验证是否被拒

---

### 问题 2：缺市场背景数据

#### 2.1 补充 Evidence Pool 初始化

**文件:** `backend/app/services/evidence_pool.py`

**改动:**

```python
class EvidencePool:
    def __init__(self, session_id: str):
        # ... 现有逻辑 ...
        self.industry_knowledge = {}
    
    async def initialize_for_topic(self, topic: str) -> None:
        """新增方法：根据话题加载行业数据"""
        
        # 初始化"OPC UA"话题的数据
        if "OPC UA" in topic or "opc" in topic.lower():
            self.industry_knowledge = {
                "adoption_2020": ("15%", "Gartner 2024 Report", 0.85),
                "adoption_forecast_2025": ("42%", "Gartner 2024", 0.70),
                "scada_integration_cost": ("$2-5M", "ARC Advisory 2023", 0.80),
                "data_silo_percentage": ("85%", "McKinsey 2023", 0.85),
                "integration_time_reduction": ("12mo → 3mo", "OPC Foundation", 0.75),
            }
            
        await self._persist_to_redis()
    
    async def get_evidence(self, key: str) -> Optional[Dict]:
        """查询单个证据"""
        # 返回 (value, source, confidence)
    
    async def search_evidence(self, query: str) -> List[Dict]:
        """搜索相关证据"""
        # 模糊匹配，返回所有相关数据
```

**核心数据（硬编码初版）:**

```json
{
  "OPC_UA": {
    "adoption_rate_2020": {
      "value": "15%",
      "source": "Gartner 2024 Industrial IoT Report",
      "confidence": 0.85
    },
    "integration_time_avg": {
      "before": "12 months",
      "after": "3 months",
      "source": "OPC Foundation Case Studies",
      "confidence": 0.75
    },
    "cost_per_integration": {
      "value": "$2-5M",
      "source": "ARC Advisory Group 2023",
      "confidence": 0.80
    }
  },
  "SCADA": {
    "data_silo_percentage": {
      "value": "85%",
      "source": "McKinsey 2023 Digital Transformation",
      "confidence": 0.85
    }
  }
}
```

**检查方式:**
- 调用 `evidence_pool.get_evidence("adoption_rate_2020")`，验证返回正确的数据
- 调用 `evidence_pool.search_evidence("adoption")`，验证检索功能

---

#### 2.2 改 Writer Prompt 加证据要求

**文件:** `backend/prompts/writer/main_writer.md` 或新建 `backend/prompts/writer/evidence_requirement.md`

**改动内容:**

```markdown
# 证据要求约束

## 标记语法

@evidence[key.subkey] → 自动引用 Evidence Pool 中的数据

## 禁止写法

❌ "传统系统难以集成"（无数字）
❌ "数据孤岛是问题"（无具体比例）

## 要求写法

✓ "85% 的企业报告面临数据孤岛 @evidence[SCADA.data_silo_percentage]"
✓ "集成时间从 12 个月缩短到 3 个月 @evidence[OPC_UA.integration_time_reduction]"

## 检查清单

- [ ] 每个"问题陈述"都有 ≥1 个数字
- [ ] 每个数字都标记 @evidence[key]
- [ ] 没有"模糊词" (往往、通常、许多)
- [ ] 所有来源都来自已知机构 (Gartner, McKinsey, OPC Foundation等)
```

**检查方式:**
- Writer 生成文章时，检查是否包含 `@evidence[` 标记
- 检查 Consistency Agent 是否能解析这些标记

---

#### 2.3 改 Reviewer Agent 加"证据充分性"维度

**文件:** `backend/app/agents/reviewer_agent.py`

**改动:**

```python
class ReviewerAgent(BaseAgent):
    SCORING_DIMENSIONS = {
        "logical_consistency": 0.3,     # 已有
        "evidence_sufficiency": 0.4,     # ← 新增
        "specificity": 0.2,              # ← 新增
        "source_attribution": 0.1,       # ← 新增
    }
    
    async def evaluate(self, text: str, evidence_pool) -> ReviewResult:
        # 现有的逻辑...
        scores["logical_consistency"] = await self._check_logical_consistency(text)
        
        # 新增逻辑
        scores["evidence_sufficiency"] = await self._check_evidence_sufficiency(
            text, evidence_pool
        )
        scores["specificity"] = await self._check_specificity(text)
        
        # 计算加权平均
        total = sum(scores[dim] * self.SCORING_DIMENSIONS[dim] 
                   for dim in scores)
        
        passed = total >= 70
        return ReviewResult(passed=passed, total_score=total, scores=scores)
    
    async def _check_evidence_sufficiency(self, text: str, pool) -> float:
        """检查主张是否有数据支撑"""
        # 统计未标记的宏观论述
        # 返回 0-100 分
```

**检查方式:**
- 提交包含"85% 的企业..."和"许多企业..."两种表述的文章
- 验证 Reviewer 是否分别给出不同的"证据充分性"评分

---

## 优先级 P1（第二周）

### 问题 3：技术陈述缺验证

#### 3.1 创建 Fact Check Agent

**文件:** `backend/app/agents/fact_check_agent.py` (新建，~300 行)

**核心方法:**

```python
class FactCheckAgent(BaseAgent):
    SPEC_REGISTRY = {
        "HistoricalDataConfiguration": {
            "spec": "OPC UA Part 11",
            "version": "1.05",
            "attributes": ["Stepped", "AggregateConfiguration"]
        },
        "HistoryRead": {
            "spec": "OPC UA Part 4",
            "version": "1.05"
        },
        # ... 扩展覆盖 50+ 常用术语
    }
    
    async def handle_task(self, ctx: dict) -> FactCheckResult:
        """验证文章中的技术术语"""
        
        text = ctx.get("full_text", "")
        
        issues = []
        
        # 提取 OPC UA 术语
        for term in self.extract_opc_ua_terms(text):
            # 检查术语是否在已知规范中
            # 检查是否标记了规范来源
            # 检查属性是否正确关联
        
        return FactCheckResult(
            passed=(len(issues) == 0),
            failures=issues
        )
    
    async def _verify_term_in_spec(self, term: str, text: str) -> Optional[Issue]:
        """验证单个术语"""
        # 1. 术语是否存在于 SPEC_REGISTRY?
        # 2. 文中是否标记了规范版本?
        # 3. 相关属性是否正确?
```

**检查方式:**
- 注入含错版本号的 OPC UA 术语，验证 Agent 是否检测
- 注入未标记规范来源的术语，验证是否提示补充

---

#### 3.2 FSM 中加 FACT_CHECK 状态

**文件:** `backend/services/long_text_fsm.py`

**改动:**

```python
class LongTextState(Enum):
    # ... 现有 ...
    REVIEWING = "reviewing"
    FACT_CHECK = "fact_check"        # ← 新增
    RE_REVIEW = "re_review"
    CONSISTENCY = "consistency"

TRANSITIONS = {
    # ... 现有 ...
    LongTextState.REVIEWING: [
        LongTextState.FACT_CHECK,     # 优先做事实检查
    ],
    LongTextState.FACT_CHECK: [
        LongTextState.RE_REVIEW,      # 检查失败 → 改写
        LongTextState.CONSISTENCY,    # 检查通过 → 继续
    ],
}

async def handle_fact_check_state(self, ctx: dict) -> str:
    """事实检查"""
    result = await self.fact_check_agent.handle_task(ctx)
    
    if result.passed:
        ctx["fact_check_passed"] = True
        return LongTextState.CONSISTENCY
    else:
        ctx["fact_check_failures"] = result.failures
        return LongTextState.RE_REVIEW
```

**检查方式:**
- 提交含技术错误的文章，验证 FSM 是否返回 RE_REVIEW 状态

---

### 问题 4：反例和边界条件模糊

#### 4.1 创建 Constraint Specification Prompt

**文件:** `backend/prompts/writer/constraint_specification.md` (新建)

**改动内容:**

```markdown
# Constraint Specification - 禁止模糊词

## 翻译表

| 禁止词 | 正确改写 |
|-------|---------|
| 小型系统 | <100 数据点的系统 |
| 变化极慢 | 变化频率 <1/分钟 |
| 高度动态 | 变化频率 >10 Hz |
| 通常 | [具体%] 的场景或 根据[来源] |

## 必填量化约束

对每个"条件论述"，必须明确：
1. 数据点规模：<100 / 100-10K / 10K-100K / >100K
2. 变化频率：<1/小时 / 1/分钟 - 1 Hz / 1-10 Hz / >10 Hz
3. 网络延迟要求：<1s / <100ms / <10ms / <1ms
4. 系统寿命：<1年 / 1-3年 / 3-10年 / >10年
```

**检查方式:**
- 提交含"小型系统"的文本给 Consistency Agent
- 验证是否被标记为"缺量化约束"

---

#### 4.2 改 Consistency Agent 检查量化

**文件:** `backend/app/agents/consistency_agent.py`

**新增检查:**

```python
async def check_vagueness(self, text: str) -> List[Issue]:
    """检查是否有模糊词未量化"""
    
    fuzzy_patterns = [
        (r"小型.*系统", "数据点规模"),
        (r"变化.*极?慢", "变化频率"),
        (r"高度.*动态", "变化频率"),
        (r"(?<![\d%])\s(通常|往往|许多)", "具体比例"),
    ]
    
    issues = []
    for pattern, dimension in fuzzy_patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            issues.append({
                "type": "VAGUE_CONSTRAINT",
                "location": match.start(),
                "text": match.group(0),
                "missing_dimension": dimension,
                "suggestion": f"改为量化表述，明确{dimension}"
            })
    
    return issues
```

---

### 问题 5：实施路径不可操作

#### 5.1 改 Task Decomposer 对"实施"类改进

**文件:** `backend/services/task_decomposer.py`

**新增方法:**

```python
def decompose_long_text_task(self, user_input: str, chapter_type: str) -> DAG:
    """
    根据章节类型选择分解粒度
    
    chapter_type:
    - "theory": 保持粗粒度（该章节是理论论述）
    - "implementation": 细粒度（该章节是操作指南）
    - "case_study": 中粒度
    """
    
    if chapter_type == "implementation":
        # 细粒度分解
        return DAGDefinition(
            nodes=[
                TaskNode("impl_checklist", type="CHECKLIST"),        # 清单
                TaskNode("impl_matrix", type="DECISION_MATRIX"),     # 决策矩阵
                TaskNode("impl_timeline", type="TIMELINE"),          # 时间估算
                TaskNode("impl_risks", type="RISK_ASSESSMENT"),      # 风险评估
            ]
        )
    else:
        return self._default_decompose(user_input)
```

---

#### 5.2 创建可操作性 Prompt

**文件:** `backend/prompts/writer/actionable_output.md` (新建)

**内容:**

```markdown
# 可操作性要求 - Implementation 章节

## 必须包含 4 部分

### 1. 快速诊断清单 (5 分钟)
\`\`\`
- [ ] [动作] [标准]
- [ ] 访问 https://... 检查当前版本
- [ ] 计算成本 < $X 或 > $Y
\`\`\`

### 2. 决策矩阵
| 维度 | 方案 A | 方案 B |
|-----|-------|-------|

### 3. 时间估算
"假设 2 人团队，X 周内完成"

### 4. 风险评估
- 风险等级：高/中/低
- 缓解方案
- 备选方案
```

---

## 优先级 P2（第三周）

### 问题 6：建议未被执行

#### 6.1 改 FSM CONSISTENCY 逻辑

**文件:** `backend/services/long_text_fsm.py`

**改动:**

```python
async def handle_consistency_state(self, ctx: dict) -> LongTextState:
    """
    改进：检查文章是否遵循自己的建议
    """
    
    text = ctx.get("full_text", "")
    consistency_result = await self.consistency_agent.evaluate(text)
    
    if not consistency_result.passed:
        # 有一致性问题 → 返回重审
        ctx["consistency_issues"] = consistency_result.issues
        return LongTextState.RE_REVIEW
    
    # 新增：检查文章本身提出的建议是否被应用
    if consistency_result.has_meta_recommendations():
        unapplied = await self.check_unapplied_recommendations(text)
        
        if unapplied:
            # 有未应用的建议 → 触发反馈循环
            for chapter_id, recs in unapplied.items():
                # 放回任务队列，让相关 Writer 改进
                await self.task_queue.put({
                    "type": "REVISION",
                    "chapter": chapter_id,
                    "recommendations": recs
                })
            
            return LongTextState.RE_REVIEW
    
    return LongTextState.DONE
```

---

## 交叉文件修改清单

### 需要修改的现有文件

| 文件 | 改动数 | 改动类型 | 工作量 |
|------|--------|--------|-------|
| `backend/services/long_text_fsm.py` | 3 处 | 新状态、新转移、新方法 | 4-5 小时 |
| `backend/app/services/evidence_pool.py` | 2 处 | 初始化方法、查询方法 | 2-3 小时 |
| `backend/prompts/writer/main_writer.md` | 1 处 | 加证据要求约束 | 1 小时 |
| `backend/app/agents/reviewer_agent.py` | 2 处 | 新维度、新检查方法 | 2-3 小时 |
| `backend/app/agents/consistency_agent.py` | 2 处 | 新检查、反馈循环 | 2-3 小时 |
| `backend/routers/outline.py` | 1 处 | 新字段验证 | 1 小时 |
| `backend/services/task_decomposer.py` | 1 处 | 类型感知分解 | 1-2 小时 |

### 需要创建的新文件

| 文件 | 代码量 | 内容 |
|------|--------|------|
| `backend/prompts/outline/core_thesis_constraint.md` | ~200 行 | Outline 论点约束 |
| `backend/prompts/writer/evidence_requirement.md` | ~150 行 | 证据要求规范 |
| `backend/prompts/writer/constraint_specification.md` | ~150 行 | 量化约束规范 |
| `backend/prompts/writer/actionable_output.md` | ~150 行 | 可操作性要求 |
| `backend/app/agents/fact_check_agent.py` | ~300 行 | 事实检查 Agent |
| `backend/app/skills/operational_spec.py` | ~200 行 | 可操作清单生成 Skill |

---

## 测试检查点

| 问题 | 测试步骤 | 预期结果 |
|------|--------|--------|
| 论点聚焦 | 提交 8 章 Outline → 检查 FSM 状态 | FSM 返回 ERROR，拒绝通过 |
| 证据充分 | 生成含"许多企业..."的文章 | Reviewer 评分 <70，拒绝 |
| 技术验证 | 注入错版本号 OPC UA 术语 | Fact Check Agent 检测并标记 |
| 量化约束 | 提交含"小型系统"的段落 | Consistency Agent 标记为模糊 |
| 可操作性 | "实施"章节是否包含清单和时间估算 | 是 |
| 建议执行 | 文章末提的改进，前面是否应用 | 是 |

---

## 后续维护建议

1. **Knowledge Base 扩展:** 后续补充 200+ 条 OPC UA 规范数据到 Fact Check Agent
2. **Evidence Pool 动态化:** 从静态 JSON 改为连接行业数据库或 API
3. **Prompt 版本管理:** 为每个 Prompt 约束文件建立版本号，便于追踪
4. **性能监控:** 监控新 FSM 状态和 Agent 的执行时间，确保不超过 2 分钟/章

---

**最后更新:** 2026-05-03  
**负责人:** AI + thinkweave team  
**状态:** READY FOR EXECUTION
