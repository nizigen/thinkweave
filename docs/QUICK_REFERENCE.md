# 诊断快速参考

**文档:** thinkweave 长文本 FSM 系统架构诊断  
**日期:** 2026-05-03  

---

## 📋 三份文档速查

### 1. `docs/SYSTEM_DIAGNOSIS.md` - 完整诊断报告
```
├─ 执行摘要 (6 个问题映射表)
├─ 6 个诊断 (每个包含)
│  ├─ 文章症状
│  ├─ 系统问题根源 (代码位置)
│  └─ 改进方案 (具体代码)
├─ 优先级和工作量估算
└─ 风险和缓解方案
```

**何时查看:** 需要理解某个问题的根本原因

---

### 2. `docs/CODE_IMPROVEMENT_CHECKLIST.md` - 代码改进清单
```
├─ P0 问题 (本周启动)
│  ├─ 问题 1: 核心论点不聚焦
│  │  ├─ 1.1 创建 core_thesis_constraint.md
│  │  ├─ 1.2 改 FSM 加 Premise Gate 状态
│  │  └─ 1.3 改 OUTLINE_REVIEW 路由
│  ├─ 问题 2: 缺市场数据
│  │  ├─ 2.1 补充 Evidence Pool 初始化
│  │  ├─ 2.2 改 Writer Prompt
│  │  └─ 2.3 改 Reviewer Agent
├─ P1 问题 (第二周)
├─ P2 问题 (第三周)
├─ 交叉文件修改清单 (13 个文件)
└─ 测试检查点
```

**何时查看:** 要开始编码实现

---

### 3. `docs/progress.md` - 项目进度
```
新增章节: "Step 9 系统诊断与改进方案"
- 核心发现表
- P0 改进方案
- 预期效果
```

**何时查看:** 追踪项目状态

---

## 🚀 立即行动清单

### 第 1 天：理解诊断（2 小时）
- [ ] 阅读 `SYSTEM_DIAGNOSIS.md` 的执行摘要
- [ ] 理解 6 个问题中的前 2 个（P0）

### 第 2-3 天：实现 P0 问题 1（4 小时）
```bash
# 创建新文件
backend/prompts/outline/core_thesis_constraint.md

# 改 FSM
backend/services/long_text_fsm.py
# → 添加 PREMISE_GATE 状态
# → 改转移规则
# → 新增 handle_premise_gate_state() 方法

# 改路由
backend/routers/outline.py
# → 改 /api/tasks/{id}/outline/confirm
# → 强制要求 approve_with_thesis 字段
```

### 第 4-5 天：实现 P0 问题 2（4 小时）
```bash
# 补充 Evidence Pool
backend/app/services/evidence_pool.py
# → 新增 initialize_for_topic() 方法
# → 硬编码 OPC UA 市场数据

# 改 Writer Prompt
backend/prompts/writer/evidence_requirement.md (新建)
# → 加 @evidence[key] 标记语法
# → 加检查清单

# 改 Reviewer
backend/app/agents/reviewer_agent.py
# → 新增 "evidence_sufficiency" 维度
# → 新增 _check_evidence_sufficiency() 方法
```

### 第 6 天：集成测试（2 小时）
```bash
# 用新 Outline 生成测试
pytest backend/tests/test_long_text_fsm.py -k "premise_gate"

# 验证证据要求
pytest backend/tests/test_reviewer_agent.py -k "evidence"
```

---

## 📊 工作量估算

| 问题 | P0/P1 | 文件数 | 小时 | 关键文件 |
|------|-------|-------|------|---------|
| 论点聚焦 | P0 | 3 | 4-5 | FSM, Outline Prompt |
| 缺数据 | P0 | 3 | 4-6 | Evidence Pool, Writer Prompt, Reviewer |
| 技术验证 | P1 | 2 | 6-8 | Fact Check Agent (新), FSM |
| 量化约束 | P1 | 1 | 2-3 | Consistency Agent |
| 可操作性 | P1 | 3 | 5-7 | Task Decomposer, Writer Prompt |
| 建议执行 | P2 | 1 | 3-4 | FSM Consistency |
| **总计** | — | **13** | **23-32h** | — |

---

## ✅ 验收标准

### P0 完成标志（第一周末）

```python
# Test 1: 论点约束
def test_8_chapters_rejected():
    outline = {
        "core_thesis": "...",
        "chapters": [
            {"title": "CH1", ...},
            {"title": "CH2", ...},
            # ... 8 个章节
        ]
    }
    result = fsm.handle_premise_gate_state({"outline": outline})
    assert result == LongTextState.OUTLINE  # 返回重写

# Test 2: 证据要求
def test_vague_statement_rejected():
    text = "许多企业面临挑战"  # 无数字
    score = reviewer.evaluate_evidence_sufficiency(text)
    assert score < 70  # 拒绝

# Test 3: 生成新文章验证
article = generate_article(
    topic="OPC UA", 
    target_words=10000,
    depth="medium"
)
assert "85%" in article  # 有具体数字
assert "@evidence[" in article or "Gartner" in article  # 有来源
assert has_clear_thesis(article)  # 有明确论点
```

---

## 🔍 常见问题

**Q: 为什么是 P0？**  
A: 这两个问题直接影响文章的"可用性"——即使完成了，用户也会问"这篇到底在讲什么？"和"这些数据从哪来的？"。修复这两个能立即提升输出质量 50%+。

**Q: 为什么要分多周实施？**  
A: 每周聚焦一个优先级，便于测试和验证。P0 修复后可立即看到改进效果，增加信心。

**Q: Evidence Pool 数据会过时吗？**  
A: 硬编码初版是快速验证概念。生产版本应连接行业数据库 API，自动更新。

**Q: 新 Agent（Fact Check）需要怎样的性能？**  
A: 应在 2-3 秒内完成单章验证（<5000 字）。使用缓存和预编译的正则表达式。

---

## 📞 快速导航

- **需要理解为什么系统会这样？** → 看 SYSTEM_DIAGNOSIS.md 的"系统问题根源"章节
- **需要开始写代码？** → 看 CODE_IMPROVEMENT_CHECKLIST.md，从 P0 开始
- **需要验证改进是否成功？** → 看最后的"测试检查点"表
- **需要看进度？** → 看 progress.md 中的"Step 9"
- **需要查看完整方案代码？** → SYSTEM_DIAGNOSIS.md 中每个问题都有具体代码示例

---

**下一步:** 选择 P0 的第一个问题，从"创建 `core_thesis_constraint.md` Prompt"开始！
