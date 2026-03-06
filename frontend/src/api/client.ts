import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    if (status === 401) {
      console.warn('未授权，请重新登录');
    } else if (status === 500) {
      console.error('服务器内部错误');
    }
    return Promise.reject(error);
  },
);

export default apiClient;
