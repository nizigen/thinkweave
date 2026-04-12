/**
 * 注册新 Agent 弹窗 — 增强视觉版
 * Ref: APP_FLOW.md — 旅程2 Agent管理
 * Ref: backend/app/schemas/agent.py — AgentCreate
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { App as AntdApp, Modal, Form, Input, InputNumber, Select, Typography } from 'antd';
import {
  RobotOutlined,
} from '@ant-design/icons';
import { motion, AnimatePresence } from 'framer-motion';
import { useAgentStore } from '../../stores/agentStore';

const { TextArea } = Input;
const { Text } = Typography;

/* ── Role → Layer/Model 自动推荐 ── */
const FALLBACK_ROLE_OPTIONS = [
  { value: 'orchestrator', label: '编排 (Orchestrator)', layer: 0, icon: '🎯', desc: '任务分解与全局协调' },
  { value: 'manager', label: '管理 (Manager)', layer: 1, icon: '📋', desc: '资源调度与策略管理' },
  { value: 'outline', label: '大纲 (Outline)', layer: 2, icon: '🗂️', desc: '结构规划与章节设计' },
  { value: 'writer', label: '写作 (Writer)', layer: 2, icon: '✍️', desc: '内容撰写与创作' },
  { value: 'reviewer', label: '审查 (Reviewer)', layer: 2, icon: '🔍', desc: '质量评分与反馈' },
  { value: 'consistency', label: '一致性 (Consistency)', layer: 2, icon: '🔗', desc: '跨章节一致性检查' },
];

const LAYER_OPTIONS = [
  { value: 0, label: 'L0 — 编排层' },
  { value: 1, label: 'L1 — 管理层' },
  { value: 2, label: 'L2 — 执行层' },
];

const LAYER_COLORS: Record<number, string> = {
  0: '#A855F7',
  1: '#6366F1',
  2: '#06B6D4',
};

interface Props {
  open: boolean;
  onClose: () => void;
  allowMutations?: boolean;
}

export default function CreateAgentModal({ open, onClose, allowMutations = true }: Props) {
  const { message } = AntdApp.useApp();
  const [form] = Form.useForm();
  const createAgent = useAgentStore((s) => s.createAgent);
  const modelOptions = useAgentStore((s) => s.modelOptions);
  const rolePresets = useAgentStore((s) => s.rolePresets);
  const skillOptions = useAgentStore((s) => s.skillOptions);
  const toolOptions = useAgentStore((s) => s.toolOptions);
  const fetchModelOptions = useAgentStore((s) => s.fetchModelOptions);
  const fetchRolePresets = useAgentStore((s) => s.fetchRolePresets);
  const fetchSkillOptions = useAgentStore((s) => s.fetchSkillOptions);
  const fetchToolOptions = useAgentStore((s) => s.fetchToolOptions);
  const [submitting, setSubmitting] = useState(false);

  const selectedRole = Form.useWatch('role', form);
  const selectedLayer = Form.useWatch('layer', form);
  const selectedModel = Form.useWatch('model', form);

  const roleOptions = useMemo(
    () =>
      rolePresets.length > 0
        ? rolePresets.map((preset) => ({
            value: preset.role,
            label: preset.label,
            layer: preset.layer,
            icon: preset.icon || '🤖',
            desc: preset.description || '',
          }))
        : FALLBACK_ROLE_OPTIONS,
    [rolePresets],
  );

  const rolePresetMap = useMemo(
    () => new Map(rolePresets.map((preset) => [preset.role, preset])),
    [rolePresets],
  );

  const rolePreset = useMemo(
    () => roleOptions.find((r) => r.value === selectedRole),
    [roleOptions, selectedRole],
  );

  const modelSelectOptions = useMemo(
    () => [
      ...modelOptions.map((option) => ({
        value: option.value,
        label: `${option.label}${option.provider ? ` (${option.provider})` : ''}`,
      })),
      { value: '__custom__', label: '自定义模型' },
    ],
    [modelOptions],
  );

  const skillSelectOptions = useMemo(
    () =>
      skillOptions.map((option) => ({
        value: option.name,
        label: `${option.name} · ${option.skill_type}`,
      })),
    [skillOptions],
  );

  const toolSelectOptions = useMemo(
    () =>
      toolOptions.map((option) => ({
        value: option.name,
        label: option.server_name
          ? `${option.name} (${option.server_name})`
          : option.name,
      })),
    [toolOptions],
  );

  useEffect(() => {
    if (!open) return;
    fetchModelOptions().catch(() => {
      message.error('加载模型选项失败');
    });
    fetchRolePresets().catch(() => {
      message.error('加载角色预设失败');
    });
    fetchSkillOptions().catch(() => {
      message.error('加载技能选项失败');
    });
    fetchToolOptions().catch(() => {
      message.error('加载 MCP 工具选项失败');
    });
  }, [open, fetchModelOptions, fetchRolePresets, fetchSkillOptions, fetchToolOptions, message]);

  useEffect(() => {
    if (!open) return;
    if (selectedModel) return;
    if (modelOptions.length === 0) return;
    form.setFieldValue('model', modelOptions[0].value);
  }, [open, selectedModel, modelOptions, form]);

  const handleRoleChange = useCallback(
    (role: string) => {
      const preset = roleOptions.find((r) => r.value === role);
      const roleDefaults = rolePresetMap.get(role);
      if (preset) {
        form.setFieldsValue({
          layer: preset.layer,
          ...(roleDefaults
            ? {
                agent_config: {
                  skill_allowlist: roleDefaults.agent_config.skill_allowlist,
                  tool_allowlist: roleDefaults.agent_config.tool_allowlist,
                  max_tool_iterations: roleDefaults.agent_config.max_tool_iterations,
                },
              }
            : {}),
        });
      }
    },
    [form, roleOptions, rolePresetMap],
  );

  const handleSubmit = useCallback(async () => {
    if (!allowMutations) {
      message.error('Admin permission required');
      return;
    }
    if (submitting) return;
    setSubmitting(true);
    try {
      const values = await form.validateFields();
      const rawConfig = values.agent_config ?? {};
      const skillAllowlist = Array.isArray(rawConfig.skill_allowlist)
        ? rawConfig.skill_allowlist
            .map((item: unknown) => String(item ?? '').trim())
            .filter(Boolean)
        : [];
      const toolAllowlist = Array.isArray(rawConfig.tool_allowlist)
        ? rawConfig.tool_allowlist
            .map((item: unknown) => String(item ?? '').trim())
            .filter(Boolean)
        : [];
      const rawIterations = Number(rawConfig.max_tool_iterations);
      const maxToolIterations = Number.isFinite(rawIterations) && rawIterations >= 1
        ? Math.floor(rawIterations)
        : undefined;
      const agentConfig =
        skillAllowlist.length > 0 || toolAllowlist.length > 0 || maxToolIterations
          ? {
              ...(skillAllowlist.length > 0 ? { skill_allowlist: skillAllowlist } : {}),
              ...(toolAllowlist.length > 0 ? { tool_allowlist: toolAllowlist } : {}),
              ...(maxToolIterations ? { max_tool_iterations: maxToolIterations } : {}),
            }
          : undefined;
      await createAgent({
        name: values.name,
        role: values.role,
        layer: values.layer,
        model: values.model === '__custom__' ? undefined : String(values.model ?? '').trim(),
        custom_model:
          values.model === '__custom__'
            ? String(values.custom_model ?? '').trim()
            : undefined,
        capabilities: values.capabilities || null,
        agent_config: agentConfig,
      });
      message.success(`Agent "${values.name}" 注册成功`);
      form.resetFields();
      onClose();
    } catch (err) {
      if (err instanceof Error) {
        message.error(err.message);
      }
    } finally {
      setSubmitting(false);
    }
  }, [form, createAgent, onClose, submitting, allowMutations]);

  const handleCancel = useCallback(() => {
    form.resetFields();
    onClose();
  }, [form, onClose]);

  const layerColor = LAYER_COLORS[selectedLayer as number] ?? '#6366F1';

  return (
    <Modal
      title={null}
      open={open}
      onOk={handleSubmit}
      onCancel={handleCancel}
      okText="确认注册"
      cancelText="取消"
      width={560}
      destroyOnClose
      styles={{
        header: { display: 'none' },
        body: { padding: 0 },
        mask: { backdropFilter: 'blur(8px)' },
      }}
      confirmLoading={submitting}
      okButtonProps={{
        disabled: submitting || !allowMutations,
        size: 'large',
        style: {
          borderRadius: 8,
          fontWeight: 600,
          paddingInline: 28,
          background: 'linear-gradient(135deg, #6366F1 0%, #818CF8 100%)',
          border: 'none',
          boxShadow: '0 4px 14px rgba(99, 102, 241, 0.35)',
        },
      }}
      cancelButtonProps={{
        size: 'large',
        style: { borderRadius: 8, borderColor: '#2A2A3E', color: '#94A3B8' },
      }}
    >
      {/* ── Visual Header ── */}
      <div
        style={{
          position: 'relative',
          padding: '32px 28px 24px',
          background: 'linear-gradient(135deg, #0F0F1A 0%, #151528 50%, #111118 100%)',
          borderBottom: '1px solid #1E1E2E',
          overflow: 'hidden',
        }}
      >
        {/* 装饰性背景网格 */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            opacity: 0.04,
            backgroundImage:
              'linear-gradient(#6366F1 1px, transparent 1px), linear-gradient(90deg, #6366F1 1px, transparent 1px)',
            backgroundSize: '24px 24px',
            maskImage: 'radial-gradient(ellipse at 30% 50%, black 0%, transparent 70%)',
            WebkitMaskImage: 'radial-gradient(ellipse at 30% 50%, black 0%, transparent 70%)',
          }}
        />
        {/* 装饰性光晕 */}
        <div
          style={{
            position: 'absolute',
            top: -40,
            right: -40,
            width: 160,
            height: 160,
            borderRadius: '50%',
            background: `radial-gradient(circle, ${layerColor}12, transparent 70%)`,
            transition: 'background 0.4s',
          }}
        />

        <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 16 }}>
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 12,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: `linear-gradient(135deg, ${layerColor}20, ${layerColor}08)`,
              border: `1px solid ${layerColor}30`,
              color: layerColor,
              fontSize: 22,
              transition: 'all 0.4s',
            }}
          >
            <RobotOutlined />
          </div>
          <div>
            <Text style={{ fontSize: 18, fontWeight: 600, color: '#F1F5F9', display: 'block' }}>
              注册新 Agent
            </Text>
            <Text style={{ fontSize: 13, color: '#64748B' }}>
              配置角色、层级与模型，加入编排系统
            </Text>
          </div>
        </div>

        {/* 选中角色预览卡片 */}
        <AnimatePresence mode="wait">
          {rolePreset && (
            <motion.div
              key={rolePreset.value}
              initial={{ opacity: 0, y: 8, height: 0, marginTop: 0 }}
              animate={{ opacity: 1, y: 0, height: 'auto', marginTop: 16 }}
              exit={{ opacity: 0, y: -4, height: 0, marginTop: 0 }}
              transition={{ duration: 0.25 }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '10px 14px',
                  borderRadius: 8,
                  background: 'rgba(99, 102, 241, 0.06)',
                  border: '1px solid rgba(99, 102, 241, 0.12)',
                }}
              >
                <span style={{ fontSize: 18 }}>{rolePreset.icon}</span>
                <div>
                  <Text style={{ color: '#CBD5E1', fontSize: 13, fontWeight: 500 }}>
                    {rolePreset.label}
                  </Text>
                  <Text style={{ color: '#64748B', fontSize: 12, display: 'block' }}>
                    {rolePreset.desc}
                  </Text>
                </div>
                <div style={{ marginLeft: 'auto' }}>
                  <Text
                    style={{
                      color: layerColor,
                      fontSize: 11,
                      fontFamily: "'JetBrains Mono', monospace",
                      fontWeight: 600,
                      padding: '2px 8px',
                      borderRadius: 4,
                      border: `1px solid ${layerColor}44`,
                    }}
                  >
                    L{rolePreset.layer}
                  </Text>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ── Form Body ── */}
      <div style={{ padding: '24px 28px 8px' }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            layer: 2,
            model: undefined,
            custom_model: '',
            agent_config: { max_tool_iterations: 1, skill_allowlist: [], tool_allowlist: [] },
          }}
          requiredMark="optional"
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入 Agent 名称' }]}
          >
            <Input placeholder="例如: Writer-1" maxLength={100} />
          </Form.Item>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <Form.Item
              name="role"
              label="角色类型"
              rules={[{ required: true, message: '请选择角色' }]}
            >
              <Select
                placeholder="选择角色"
                options={roleOptions}
                onChange={handleRoleChange}
              />
            </Form.Item>

            <Form.Item
              name="layer"
              label="层级"
              rules={[{ required: true, message: '请选择层级' }]}
            >
              <Select options={LAYER_OPTIONS} />
            </Form.Item>
          </div>

          <Form.Item
            name="model"
            label="LLM 模型"
            rules={[{ required: true, message: '请选择模型' }]}
          >
            <Select
              placeholder="选择模型"
              options={modelSelectOptions}
              optionFilterProp="label"
              showSearch
            />
          </Form.Item>

          {selectedModel === '__custom__' ? (
            <Form.Item
              name="custom_model"
              label="自定义模型名"
              rules={[
                { required: true, message: '请输入自定义模型名' },
                { max: 100, message: '模型名最多 100 个字符' },
              ]}
            >
              <Input placeholder="例如：openrouter/anthropic/claude-sonnet-4" />
            </Form.Item>
          ) : null}

          <Form.Item name="capabilities" label="能力描述">
            <TextArea
              rows={3}
              placeholder="描述该 Agent 的专长和能力，用于任务分配时参考..."
              maxLength={500}
              showCount
            />
          </Form.Item>

          <div style={{ marginTop: 8, padding: '12px 14px', border: '1px solid #1E1E2E', borderRadius: 8, background: '#0F172A22' }}>
            <Text style={{ color: '#CBD5E1', fontSize: 13, fontWeight: 500, display: 'block', marginBottom: 12 }}>
              技能与 MCP 注入
            </Text>

            <Form.Item name={['agent_config', 'skill_allowlist']} label="Skill 注入白名单">
              <Select
                mode="multiple"
                placeholder="选择一个或多个 Skill（可留空使用自动匹配）"
                options={skillSelectOptions}
                optionFilterProp="label"
                showSearch
              />
            </Form.Item>

            <Form.Item name={['agent_config', 'tool_allowlist']} label="MCP 工具白名单">
              <Select
                mode="tags"
                placeholder="选择或输入 MCP 工具名，例如 web_fetch"
                options={toolSelectOptions}
                optionFilterProp="label"
                showSearch
              />
            </Form.Item>

            <Form.Item
              name={['agent_config', 'max_tool_iterations']}
              label="MCP 最大迭代次数"
              tooltip="单次任务中工具调用循环最大轮数"
            >
              <InputNumber min={1} max={50} style={{ width: '100%' }} />
            </Form.Item>
          </div>
        </Form>
      </div>
    </Modal>
  );
}
