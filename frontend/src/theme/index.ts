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
    colorTextTertiary: '#64748B',
    colorSuccess: '#10B981',
    colorWarning: '#F59E0B',
    colorError: '#EF4444',
    colorInfo: '#3B82F6',
    borderRadius: 8,
    fontFamily: "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
    fontSize: 14,
    colorBgMask: 'rgba(0, 0, 0, 0.75)',
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
    Modal: {
      contentBg: '#111118',
      headerBg: '#111118',
      titleColor: '#F1F5F9',
      titleFontSize: 16,
    },
    Input: {
      colorBgContainer: '#0D0D14',
      activeBorderColor: '#6366F1',
      hoverBorderColor: '#3A3A5C',
      activeShadow: '0 0 0 2px rgba(99, 102, 241, 0.15)',
    },
    InputNumber: {
      colorBgContainer: '#0D0D14',
      activeBorderColor: '#6366F1',
      hoverBorderColor: '#3A3A5C',
    },
    Select: {
      colorBgContainer: '#0D0D14',
      colorBgElevated: '#151520',
      optionSelectedBg: '#1F1F2E',
      optionActiveBg: '#1A1A26',
      selectorBg: '#0D0D14',
    },
    Table: {
      headerBg: '#0F0F18',
      headerColor: '#94A3B8',
      rowHoverBg: '#1A1A26',
      borderColor: '#1E1E2E',
      colorBgContainer: '#111118',
    },
    Form: {
      labelColor: '#CBD5E1',
    },
    Button: {
      primaryShadow: '0 2px 8px rgba(99, 102, 241, 0.25)',
    },
    Drawer: {
      colorBgElevated: '#0A0A0F',
    },
    Popconfirm: {
      colorTextHeading: '#F1F5F9',
    },
    Descriptions: {
      colorTextSecondary: '#94A3B8',
    },
    Tooltip: {
      colorBgSpotlight: '#1A1A26',
    },
  },
};
