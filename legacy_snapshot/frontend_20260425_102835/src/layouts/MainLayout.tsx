/**
 * 主布局：顶部导航栏(64px) + 左侧导航(240px) + 主内容区
 * 参考：FRONTEND_GUIDELINES.md — 布局规范
 */
import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu } from 'antd';
import {
  PlusCircleOutlined,
  TeamOutlined,
  HistoryOutlined,
} from '@ant-design/icons';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: '/', icon: <PlusCircleOutlined />, label: '任务创建' },
  { key: '/agents', icon: <TeamOutlined />, label: 'Agent 管理' },
  { key: '/history', icon: <HistoryOutlined />, label: '历史任务' },
];

export default function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  const selectedKey = menuItems.find((item) =>
    location.pathname === item.key
  )?.key ?? '/';

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          height: 64,
          display: 'flex',
          alignItems: 'center',
          padding: '0 24px',
          borderBottom: '1px solid #1E1E2E',
        }}
      >
        <div
          style={{
            color: '#F1F5F9',
            fontSize: 18,
            fontWeight: 600,
            letterSpacing: 1,
          }}
        >
          Hierarch
        </div>
      </Header>
      <Layout>
        <Sider
          width={240}
          collapsible
          collapsed={collapsed}
          onCollapse={setCollapsed}
          style={{ borderRight: '1px solid #1E1E2E' }}
        >
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{ marginTop: 8 }}
          />
        </Sider>
        <Content style={{ padding: 24, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
