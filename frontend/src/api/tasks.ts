import apiClient from './client';
import type { Task } from '../stores/taskStore';

export async function getTask(taskId: string): Promise<Task> {
  const response = await apiClient.get<Task>(`/tasks/${taskId}`);
  return response.data;
}
