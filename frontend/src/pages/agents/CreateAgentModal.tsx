/**
 * 注册新 Agent 弹窗
 * Ref: APP_FLOW.md — 旅程2 Agent管理
 * Ref: backend/app/schemas/agent.py — AgentCreate
 */
import { useCallback } from 'react';
import { Modal, Form, Input, Select, message } from 'antd';
import { useAgentStore } from '../../stores/agentStore';

const { TextArea } = Input;

/* ── Role → Layer/Model 自动推荐 ── */
const ROLE_OPTIONS = [
  { value: 'orchestrator', label: '编排 (Orchestrator)', layer: 0, model: 'gpt-4o' },
  { value: 'manager', label: '管理 (Manager)', layer: 1, model: 'deepseek-v3.2' },
  { value: 'outline', label: '大纲 (Outline)', layer: 2, model: 'gpt-4o' },
  { value: 'writer', label: '写作 (Writer)', layer: 2, model: 'deepseek-v3.2' },
  { value: 'reviewer', label: '审查 (Reviewer)', layer: 2, model: 'gpt-4o' },
  { value: 'consistency', label: '一致性 (Consistency)', layer: 2, model: 'gpt-4o' },
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

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function CreateAgentModal({ open, onClose }: Props) {
  const [form] = Form.useForm();
  const createAgent = useAgentStore((s) => s.createAgent);

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

  return (
    <Modal
      title="注册新 Agent"
      open={open}
      onOk={handleSubmit}
      onCancel={handleCancel}
      okText="确认注册"
      cancelText="取消"
      width={520}
      destroyOnClose
      styles={{
        header: { borderBottom: '1px solid #2A2A3E', paddingBottom: 16 },
        body: { paddingTop: 24 },
        mask: { backdropFilter: 'blur(4px)' },
      }}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ layer: 2, model: 'gpt-4o' }}
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

        <Form.Item
          name="model"
          label="LLM 模型"
          rules={[{ required: true, message: '请选择模型' }]}
        >
          <Select options={MODEL_OPTIONS} />
        </Form.Item>

        <Form.Item name="capabilities" label="能力描述">
          <TextArea
            rows={3}
            placeholder="描述该 Agent 的专长和能力，用于任务分配时参考..."
            maxLength={500}
            showCount
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
