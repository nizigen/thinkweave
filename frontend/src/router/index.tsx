/**
 * 路由配置
 * 参考：APP_FLOW.md — 页面路由表
 */
import { createBrowserRouter } from 'react-router-dom';
import MainLayout from '../layouts/MainLayout';
import Home from '../pages/Home';
import Monitor from '../pages/Monitor';
import Result from '../pages/Result';
import Outline from '../pages/Outline';
import Agents from '../pages/Agents';
import History from '../pages/History';

const router = createBrowserRouter([
  {
    path: '/',
    element: <MainLayout />,
    children: [
      { index: true, element: <Home /> },
      { path: 'monitor/:taskId', element: <Monitor /> },
      { path: 'result/:taskId', element: <Result /> },
      { path: 'task/:taskId/outline', element: <Outline /> },
      { path: 'agents', element: <Agents /> },
      { path: 'history', element: <History /> },
    ],
  },
]);

export default router;
