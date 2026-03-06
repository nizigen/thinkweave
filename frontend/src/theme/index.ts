/**
 * Ant Design 暗色主题配置
 * 参考：FRONTEND_GUIDELINES.md — 颜色系统 + Ant Design 覆盖配置
 */
import { theme } from 'antd';
import type { ThemeConfig } from 'antd';

export const antdTheme: ThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#6366F1',
    colorBgBase: '#0A0A0F',
    colorBgContainer: '#111118',
    colorBgElevated: '#1A1A26',
    colorBorder: '#2A2A3E',
    colorBorderSecondary: '#1E1E2E',
    colorText: '#F1F5F9',
    colorTextSecondary: '#94A3B8',
    colorTextTertiary: '#475569',
    colorSuccess: '#10B981',
    colorWarning: '#F59E0B',
    colorError: '#EF4444',
    colorInfo: '#3B82F6',
    borderRadius: 8,
    fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    fontSize: 14,
  },
  components: {
    Layout: {
      siderBg: '#111118',
      headerBg: '#0A0A0F',
      bodyBg: '#0A0A0F',
    },
    Menu: {
      darkItemBg: '#111118',
      darkItemSelectedBg: '#1F1F2E',
      darkItemHoverBg: '#1A1A26',
    },
  },
};
