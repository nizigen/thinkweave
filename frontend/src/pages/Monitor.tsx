import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Alert, Space, Tag, Typography } from 'antd';

import {
  pauseTask,
  resumeTask,
  retryTaskNode,
  skipTaskNode,
} from '../api/tasks';
import { AgentPanel } from '../components/monitor/AgentPanel';
import { ChapterPreview } from '../components/monitor/ChapterPreview';
import { ControlToolbar } from '../components/monitor/ControlToolbar';
import { DagViewer } from '../components/monitor/DagViewer';
import { FsmProgress } from '../components/monitor/FsmProgress';
import { LogStream } from '../components/monitor/LogStream';
import { useTaskWebSocket } from '../hooks/useTaskWebSocket';
import { useMonitorStore } from '../stores/monitorStore';
import type { Task } from '../stores/taskStore';

const { Title } = Typography;

export default function Monitor() {
  const { taskId } = useParams<{ taskId: string }>();
  const { connectionState, reconnectAttempt, lastError } = useTaskWebSocket(taskId);
  const taskSnapshot = useMonitorStore((state) => state.taskSnapshot);
  const orderedNodeIds = useMonitorStore((state) => state.orderedNodeIds);
  const selectedNodeId = useMonitorStore((state) => state.selectedNodeId);
  const selectNode = useMonitorStore((state) => state.selectNode);
  const setTaskSnapshot = useMonitorStore((state) => state.setTaskSnapshot);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<
    'pause' | 'resume' | 'skip' | 'retry' | null
  >(null);
  const isMountedRef = useRef(true);

  useEffect(
    () => () => {
      isMountedRef.current = false;
    },
    [],
  );

  useEffect(() => {
    if (!selectedNodeId && orderedNodeIds.length > 0) {
      selectNode(orderedNodeIds[0] ?? null);
    }
  }, [orderedNodeIds, selectedNodeId, selectNode]);

  const runControlAction = async (
    action: 'pause' | 'resume' | 'skip' | 'retry',
    requestedTaskId: string,
    request: () => Promise<Task>,
  ) => {
    setActionError(null);
    setBusyAction(action);
    try {
      const task = await request();
      if (
        !isMountedRef.current ||
        useMonitorStore.getState().activeTaskId !== requestedTaskId
      ) {
        return;
      }
      setTaskSnapshot(task);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Monitor control request failed';
      setActionError(message);
    } finally {
      setBusyAction(null);
    }
  };

  const handlePause = () => {
    if (!taskId) {
      return;
    }
    void runControlAction('pause', taskId, () => pauseTask(taskId));
  };

  const handleResume = () => {
    if (!taskId) {
      return;
    }
    void runControlAction('resume', taskId, () => resumeTask(taskId));
  };

  const handleSkip = () => {
    if (!taskId || !selectedNodeId) {
      return;
    }
    void runControlAction('skip', taskId, () => skipTaskNode(taskId, selectedNodeId));
  };

  const handleRetry = () => {
    if (!taskId || !selectedNodeId) {
      return;
    }
    void runControlAction('retry', taskId, () => retryTaskNode(taskId, selectedNodeId));
  };

  return (
    <Space direction="vertical" size="large" className="monitor-page">
      <div className="monitor-page-header">
        <div>
          <Title level={3} style={{ marginBottom: 0 }}>
            Control Tower
          </Title>
          <Typography.Text type="secondary">
            编排监控任务 {taskId}
          </Typography.Text>
        </div>
        <Space wrap>
          <Tag color={connectionState === 'connected' ? 'success' : 'processing'}>
            Connection {connectionState}
          </Tag>
          <Tag color="blue">Reconnect {reconnectAttempt}</Tag>
          <Tag color="purple">FSM {taskSnapshot?.fsm_state ?? 'pending'}</Tag>
        </Space>
      </div>

      {lastError ? <Alert type="error" showIcon message={lastError} /> : null}
      {actionError ? <Alert type="error" showIcon message={actionError} /> : null}

      <div className="monitor-grid monitor-grid-top">
        <div>
          <FsmProgress />
        </div>
        <div>
          <ControlToolbar
            onPause={handlePause}
            onResume={handleResume}
            onSkip={handleSkip}
            onRetry={handleRetry}
            busyAction={busyAction}
          />
        </div>
      </div>

      <div className="monitor-grid monitor-grid-main">
        <div>
          <DagViewer />
        </div>
        <div>
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <AgentPanel />
            <LogStream />
          </Space>
        </div>
      </div>

      <ChapterPreview />
    </Space>
  );
}
