# FRONTEND_GUIDELINES.md — 前端设计规范

## 设计理念

**科技感 + 专业感**：参考 Vercel Dashboard、Linear、Perplexity 的设计风格。
深色主题为主，数据可视化突出，动效克制但有质感。

---

## 颜色系统

### 主题色（深色模式 — OLED高对比）

设计风格：**Dark Mode (OLED)**，参考 Vercel / Linear / Raycast 的深色界面。
核心原则：背景极深、文字高亮、主色克制点缀、微光效果增加层次。

```css
/* 背景层级（5层递进） */
--bg-base:        #0A0A0F;   /* 最底层背景（Layout body） */
--bg-deep:        #0D0D14;   /* 输入框/嵌套区域深层背景 */
--bg-surface:     #111118;   /* 卡片/面板/表格背景 */
--bg-elevated:    #1A1A26;   /* 悬浮元素/Tooltip背景 */
--bg-hover:       #1F1F2E;   /* hover/selected状态 */

/* 边框（3层递进） */
--border-subtle:  #1A1A26;   /* 分组内细分割线 */
--border-default: #2A2A3E;   /* 默认边框 */
--border-strong:  #3A3A5C;   /* hover边框 / 强调边框 */

/* 主色调（紫色系） */
--primary-500:    #6366F1;   /* 主色 */
--primary-400:    #818CF8;   /* hover */
--primary-300:    #A5B4FC;   /* 浅色/禁用 */
--primary-600:    #4F46E5;   /* active */
--primary-glow:   rgba(99, 102, 241, 0.15);  /* 聚焦光晕 */

/* 文字层级（5级） */
--text-heading:   #F8FAFC;   /* 标题/数值/强调 — 最亮 */
--text-primary:   #F1F5F9;   /* 主要正文 */
--text-secondary: #CBD5E1;   /* 表单label / 卡片标题 */
--text-muted:     #94A3B8;   /* 次要描述 / 表头 */
--text-disabled:  #64748B;   /* 占位符 / 禁用态 (WCAG 4.5:1) */

/* 语义色 */
--success:        #10B981;   /* 完成/空闲 */
--warning:        #F59E0B;   /* 警告/审查 */
--error:          #EF4444;   /* 失败/错误 */
--info:           #3B82F6;   /* 执行中/忙碌 */
--pending:        #6B7280;   /* 待执行/离线 */
```

### 对比度合规（WCAG AA）

| 变量 | 色值 | 对比度 vs #0A0A0F | 用途 |
|------|------|-------------------|------|
| `--text-heading` | `#F8FAFC` | 18.5:1 | 标题、数值 |
| `--text-primary` | `#F1F5F9` | 16.8:1 | 正文 |
| `--text-secondary` | `#CBD5E1` | 11.2:1 | Label、副文本 |
| `--text-muted` | `#94A3B8` | 6.4:1 | 表头、描述 |
| `--text-disabled` | `#64748B` | 4.5:1 | 占位符（AA最低线） |

### DAG节点状态色

| 状态 | 颜色 | 色值 |
|------|------|------|
| 待执行 | 灰色 | `#374151` |
| 执行中 | 蓝色脉冲 | `#3B82F6` |
| 完成 | 绿色 | `#10B981` |
| 失败 | 红色 | `#EF4444` |
| 审查中/警告 | 橙色 | `#F59E0B` |

---

## 字体系统

```css
/* 字体族 */
--font-sans: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', monospace;

/* 字号刻度 */
--text-xs:   12px;  /* 标签、辅助信息 */
--text-sm:   14px;  /* 正文、表格内容 */
--text-base: 16px;  /* 默认正文 */
--text-lg:   18px;  /* 小标题 */
--text-xl:   20px;  /* 页面副标题 */
--text-2xl:  24px;  /* 页面标题 */
--text-3xl:  30px;  /* 大标题 */

/* 字重 */
--font-normal:   400;
--font-medium:   500;
--font-semibold: 600;
--font-bold:     700;
```

---

## 间距系统

使用 4px 基础单位：

```css
--space-1:  4px;
--space-2:  8px;
--space-3:  12px;
--space-4:  16px;
--space-5:  20px;
--space-6:  24px;
--space-8:  32px;
--space-10: 40px;
--space-12: 48px;
--space-16: 64px;
```

---

## 圆角

```css
--radius-sm:  4px;   /* 标签、小按钮 */
--radius-md:  8px;   /* 卡片、输入框 */
--radius-lg:  12px;  /* 大卡片、模态框 */
--radius-xl:  16px;  /* 特殊容器 */
--radius-full: 9999px; /* 徽章、头像 */
```

---

## 响应式断点

```css
--bp-sm:  640px;   /* 小屏 */
--bp-md:  768px;   /* 平板 */
--bp-lg:  1024px;  /* 桌面 */
--bp-xl:  1280px;  /* 宽屏 */
--bp-2xl: 1536px;  /* 超宽屏 */
```

本项目主要针对 1280px+ 桌面端，不做移动端适配。

---

## 布局规范

### 整体布局
```
┌─────────────────────────────────────────┐
│  顶部导航栏（64px固定高度）              │
├──────────┬──────────────────────────────┤
│ 左侧导航 │  主内容区                    │
│ (240px)  │  padding: 24px               │
│  固定    │                              │
└──────────┴──────────────────────────────┘
```

### 监控页布局（核心页面）
```
┌─────────────────────────────────────────┐
│  进度条（FSM阶段）                       │
├────────────────────┬────────────────────┤
│                    │  Agent 活动面板     │
│   DAG 图          │  (实时更新)         │
│   (G6渲染)        ├────────────────────┤
│                    │  执行日志流         │
│                    │  (滚动)             │
└────────────────────┴────────────────────┘
```

---

## 组件规范

### 按钮
- Primary: 主色背景 + 白色文字 + hover变深
- Secondary: 透明背景 + 主色边框 + 主色文字
- Danger: 红色背景
- 尺寸：sm(28px) / md(36px) / lg(44px)
- 禁用状态：opacity 0.5，cursor not-allowed

### 状态徽章
```
待执行: 灰色圆点 + "Pending"
执行中: 蓝色脉冲动画 + "Running"
完成:   绿色实心 + "Done"
失败:   红色实心 + "Failed"
```

### DAG节点样式
- 圆角矩形，宽160px
- 节点内显示：任务名（最多2行）+ 负责Agent名
- 边（Edge）：带箭头的曲线，颜色随源节点状态变化
- 执行中节点：边框发光动画（box-shadow pulse）

### 日志流
- monospace字体
- 每行：`[时间] [AgentName] 内容`
- Agent名用对应颜色标识（每个Agent固定一个颜色）
- 自动滚动到底部，可手动暂停

---

## 动效规范

| 场景 | 动效 | 时长 |
|------|------|------|
| 页面切换 | fade + slide up | 200ms |
| 节点状态变化 | 颜色过渡 | 300ms |
| 执行中节点 | border pulse | 1.5s loop |
| 日志新增 | fade in | 150ms |
| 模态框 | scale + fade | 200ms |
| 按钮hover | brightness变化 | 150ms |

所有动效使用 CSS transition 或 framer-motion，禁止使用 jQuery 动画。

---

## Ant Design 覆盖配置

所有配置集中于 `theme/index.ts`，配合 `index.css` 处理深层 DOM 节点。

```typescript
// theme/index.ts — 完整配置
export const antdTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#6366F1',
    colorBgBase: '#0A0A0F',          // --bg-base
    colorBgContainer: '#111118',      // --bg-surface
    colorBgElevated: '#1A1A26',       // --bg-elevated
    colorBorder: '#2A2A3E',           // --border-default
    colorBorderSecondary: '#1E1E2E',
    colorText: '#F1F5F9',             // --text-primary
    colorTextSecondary: '#94A3B8',    // --text-muted
    colorTextTertiary: '#64748B',     // --text-disabled (WCAG 4.5:1)
    colorBgMask: 'rgba(0, 0, 0, 0.75)', // Modal遮罩
    borderRadius: 8,
    fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    fontSize: 14,
  },
  components: {
    Layout:      { siderBg: '#111118', headerBg: '#0A0A0F', bodyBg: '#0A0A0F' },
    Menu:        { darkItemBg: '#111118', darkItemSelectedBg: '#1F1F2E', darkItemHoverBg: '#1A1A26' },
    Modal:       { contentBg: '#111118', headerBg: '#111118', titleColor: '#F1F5F9' },
    Drawer:      { colorBgElevated: '#0A0A0F' },
    Input:       { colorBgContainer: '#0D0D14', activeBorderColor: '#6366F1', hoverBorderColor: '#3A3A5C' },
    InputNumber: { colorBgContainer: '#0D0D14', activeBorderColor: '#6366F1' },
    Select:      { colorBgContainer: '#0D0D14', colorBgElevated: '#151520', optionSelectedBg: '#1F1F2E', selectorBg: '#0D0D14' },
    Table:       { headerBg: '#0F0F18', headerColor: '#94A3B8', rowHoverBg: '#1A1A26', colorBgContainer: '#111118' },
    Form:        { labelColor: '#CBD5E1' },
    Button:      { primaryShadow: '0 2px 8px rgba(99, 102, 241, 0.25)' },
    Tooltip:     { colorBgSpotlight: '#1A1A26' },
  },
};
```

### CSS 深层覆盖（index.css）

Token 无法覆盖的深层 Ant Design DOM 节点，通过 CSS `!important` 统一处理：

| 目标 | 关键样式 |
|------|----------|
| `.ant-modal-content` | `background: #111118`, 圆角16px, 发光阴影 |
| `.ant-modal-close:hover` | `background: rgba(255,255,255,0.06)` |
| `.ant-table-thead > tr > th` | uppercase, letter-spacing, `#0F0F18` |
| `.ant-table-tbody > tr:hover td:first-child` | 左侧紫色指示条 `inset 3px 0 0 #6366F1` |
| `.ant-select-dropdown` | `#151520` 背景 + `#2A2A3E` 边框 |
| `.ant-input::placeholder` | `#475569` |
| 所有表单元素 focus | `box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.15)` |

### 装饰效果约定

| 效果 | 用法 | 实现 |
|------|------|------|
| 顶部色条 | 卡片/Modal顶部 | `linear-gradient(90deg, {color}00, {color}60, {color}00)`, height 2px |
| 网格纹理 | Modal/卡片头部背景 | `repeating-linear-gradient` 20px网格, opacity 0.03-0.06 |
| 径向光晕 | 交互焦点区域 | `radial-gradient(circle at 50% 0%, {color}15, transparent 70%)` |
| 悬浮发光 | 卡片hover | `box-shadow: 0 0 24px {color}20, inset 0 1px 0 {color}15` |
| 进度条 | 统计卡片底部 | `linear-gradient(90deg, {color}, {color}80)`, animated width |

## 流程可视化增强（2026-03-21）

### 1. 阶段条扩展
1. 在主进度条增加节点：`2.5 Integrity`、`3' Re-review`、`4' Re-revise`、`4.5 Final Integrity`。
2. 对 MANDATORY 关卡使用高亮边框和锁图标。

### 2. Checkpoint 组件规范
1. FULL 卡片：展示阶段产物列表、质量分、风险项、下一步动作。
2. SLIM 条：只显示“阶段完成 + 5s 自动继续”提示。
3. MANDATORY 弹窗：必须显式点击，禁止自动关闭。

### 3. 审查与修订联动视图
1. 新增“问题闭环表”：`问题 -> 修改动作 -> 证据`。
2. 支持按章节过滤，支持“未闭环问题”红色标记。
3. 增加“完整性关卡结果卡片”：展示 blocking issues 数量和最近一次校验时间。
