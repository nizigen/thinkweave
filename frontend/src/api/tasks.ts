import apiClient from './client';
import type { Task } from '../stores/taskStore';

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
