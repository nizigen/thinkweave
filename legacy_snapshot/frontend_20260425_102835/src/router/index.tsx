/**
 * 路由配置
 * 参考：APP_FLOW.md — 页面路由表
 */
/* eslint-disable react-refresh/only-export-components */
import { Suspense, lazy, type ReactNode } from 'react';
import { createBrowserRouter } from 'react-router-dom';
import MainLayout from '../layouts/MainLayout';

const Home = lazy(() => import('../pages/Home'));
const Monitor = lazy(() => import('../pages/Monitor'));
const Result = lazy(() => import('../pages/Result'));
const Outline = lazy(() => import('../pages/Outline'));
const Agents = lazy(() => import('../pages/Agents'));
const History = lazy(() => import('../pages/History'));

function withSuspense(element: ReactNode) {
  return (
    <Suspense fallback={<div style={{ padding: 24, color: '#94A3B8' }}>加载中...</div>}>
      {element}
    </Suspense>
  );
}

const router = createBrowserRouter([
  {
    path: '/',
    element: <MainLayout />,
    children: [
      { index: true, element: withSuspense(<Home />) },
      { path: 'monitor/:taskId', element: withSuspense(<Monitor />) },
      { path: 'result/:taskId', element: withSuspense(<Result />) },
      { path: 'task/:taskId/outline', element: withSuspense(<Outline />) },
      { path: 'agents', element: withSuspense(<Agents />) },
      { path: 'history', element: withSuspense(<History />) },
    ],
  },
]);

export default router;
