import { ConfigProvider } from 'antd';
import { RouterProvider } from 'react-router-dom';
import { antdTheme } from './theme';
import router from './router';

export default function App() {
  return (
    <ConfigProvider theme={antdTheme}>
      <RouterProvider router={router} />
    </ConfigProvider>
  );
}
