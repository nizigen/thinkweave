/**
 * 注册新 Agent 弹窗 — 增强视觉版
 * Ref: APP_FLOW.md — 旅程2 Agent管理
 * Ref: backend/app/schemas/agent.py — AgentCreate
 */
import { useCallback, useMemo } from 'react';
import { Modal, Form, Input, Select, message, Typography } from 'antd';
import {
  RobotOutlined,
  ThunderboltOutlined,
  AppstoreOutlined,
  ApiOutlined,
} from '@ant-design/icons';
import { motion, AnimatePresence } from 'framer-motion';
import { useAgentStore } from '../../stores/agentStore';

const { TextArea } = Input;
const { Text } = Typography;

/* ── Role → Layer/Model 自动推荐 ── */
const ROLE_OPTIONS = [
  { value: 'orchestrator', label: '编排 (Orchestrator)', layer: 0, model: 'gpt-4o', icon: '🎯', desc: '任务分解与全局协调' },
  { value: 'manager', label: '管理 (Manager)', layer: 1, model: 'deepseek-v3.2', icon: '📋', desc: '资源调度与策略管理' },
  { value: 'outline', label: '大纲 (Outline)', layer: 2, model: 'gpt-4o', icon: '🗂️', desc: '结构规划与章节设计' },
  { value: 'writer', label: '写作 (Writer)', layer: 2, model: 'deepseek-v3.2', icon: '✍️', desc: '内容撰写与创作' },
  { value: 'reviewer', label: '审查 (Reviewer)', layer: 2, model: 'gpt-4o', icon: '🔍', desc: '质量评分与反馈' },
  { value: 'consistency', label: '一致性 (Consistency)', layer: 2, model: 'gpt-4o', icon: '🔗', desc: '跨章节一致性检查' },
];

const LAYER_OPTIONS = [
  { value: 0, label: 'L0 — 编排层' },
  { value: 1, label: 'L1 — 管理层' },
  { value: 2, label: 'L2 — 执行层' },
];

const MODEL_OPTIONS = [
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'deepseek-v3.2', label: 'DeepSeek-V3.2' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
];

const LAYER_COLORS: Record<number, string> = {
  0: '#A855F7',
  1: '#6366F1',
  2: '#06B6D4',
};

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function CreateAgentModal({ open, onClose }: Props) {
  const [form] = Form.useForm();
  const createAgent = useAgentStore((s) => s.createAgent);

  const selectedRole = Form.useWatch('role', form);
  const selectedLayer = Form.useWatch('layer', form);

  const rolePreset = useMemo(
    () => ROLE_OPTIONS.find((r) => r.value === selectedRole),
    [selectedRole],
  );

  const handleRoleChange = useCallback(
    (role: string) => {
      const preset = ROLE_OPTIONS.find((r) => r.value === role);
      if (preset) {
        form.setFieldsValue({ layer: preset.layer, model: preset.model });
      }
    },
    [form],
  );

  const handleSubmit = useCallback(async () => {
    try {
      const values = await form.validateFields();
      await createAgent({
        name: values.name,
        role: values.role,
        layer: values.layer,
        model: values.model,
        capabilities: values.capabilities || null,
      });
      message.success(`Agent "${values.name}" 注册成功`);
      form.resetFields();
      onClose();
    } catch (err) {
      if (err instanceof Error) {
        message.error(err.message);
      }
    }
  }, [form, createAgent, onClose]);

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
      okButtonProps={{
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
          initialValues={{ layer: 2, model: 'gpt-4o' }}
          requiredMark="optional"
        >
          {/* 基本信息区块 */}
          <div
            style={{
              marginBottom: 20,
              padding: '16px 16px 4px',
              borderRadius: 10,
              background: '#0D0D14',
              border: '1px solid #1A1A26',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <ThunderboltOutlined style={{ color: '#6366F1', fontSize: 13 }} />
              <Text style={{ color: '#94A3B8', fontSize: 12, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                基本信息
              </Text>
            </div>

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
                  options={ROLE_OPTIONS}
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
          </div>

          {/* 模型配置区块 */}
          <div
            style={{
              marginBottom: 20,
              padding: '16px 16px 4px',
              borderRadius: 10,
              background: '#0D0D14',
              border: '1px solid #1A1A26',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <AppstoreOutlined style={{ color: '#10B981', fontSize: 13 }} />
              <Text style={{ color: '#94A3B8', fontSize: 12, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                模型配置
              </Text>
            </div>

            <Form.Item
              name="model"
              label="LLM 模型"
              rules={[{ required: true, message: '请选择模型' }]}
            >
              <Select options={MODEL_OPTIONS} />
            </Form.Item>
          </div>

          {/* 能力描述区块 */}
          <div
            style={{
              marginBottom: 4,
              padding: '16px 16px 4px',
              borderRadius: 10,
              background: '#0D0D14',
              border: '1px solid #1A1A26',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <ApiOutlined style={{ color: '#F59E0B', fontSize: 13 }} />
              <Text style={{ color: '#94A3B8', fontSize: 12, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                能力定义
              </Text>
            </div>

            <Form.Item name="capabilities" label="能力描述">
              <TextArea
                rows={3}
                placeholder="描述该 Agent 的专长和能力，用于任务分配时参考..."
                maxLength={500}
                showCount
              />
            </Form.Item>
          </div>
        </Form>
      </div>
    </Modal>
  );
}
