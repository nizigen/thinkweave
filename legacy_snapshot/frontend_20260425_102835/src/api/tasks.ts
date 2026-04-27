import apiClient from './client';
import type { Task } from '../stores/taskStore';

export interface TaskListParams {
  offset?: number;
  limit?: number;
  status?: string;
  mode?: string;
  search?: string;
}

export interface TaskListResult {
  items: Task[];
  total: number;
}

export interface BatchDeleteResult {
  deleted_count: number;
}

export async function listTasks(params?: TaskListParams): Promise<TaskListResult> {
  const response = await apiClient.get<TaskListResult>('/tasks', { params });
  return response.data;
}

export async function batchDeleteTasks(ids: string[]): Promise<BatchDeleteResult> {
  const response = await apiClient.delete<BatchDeleteResult>('/tasks', { data: { ids } });
  return response.data;
}

export async function getTask(taskId: string): Promise<Task> {
  const response = await apiClient.get<Task>(`/tasks/${taskId}`);
  return response.data;
}

export async function pauseTask(taskId: string): Promise<Task> {
  const response = await apiClient.post<Task>(`/tasks/${taskId}/control/pause`);
  return response.data;
}

export async function resumeTask(taskId: string): Promise<Task> {
  const response = await apiClient.post<Task>(`/tasks/${taskId}/control/resume`);
  return response.data;
}

export async function skipTaskNode(taskId: string, nodeId: string): Promise<Task> {
  const response = await apiClient.post<Task>(`/tasks/${taskId}/control/skip`, {
    node_id: nodeId,
  });
  return response.data;
}

export async function retryTaskNode(taskId: string, nodeId: string): Promise<Task> {
  const response = await apiClient.post<Task>(`/tasks/${taskId}/control/retry`, {
    node_id: nodeId,
  });
  return response.data;
}
