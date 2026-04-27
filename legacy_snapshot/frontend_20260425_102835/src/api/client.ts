import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('task_auth_token') || '';
  if (token) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    if (status === 401) {
      console.warn('Unauthorized request');
    } else if (status === 403) {
      console.warn('Forbidden request');
    } else if (status === 500) {
      console.error('Server error');
    }
    return Promise.reject(error);
  },
);

export default apiClient;
