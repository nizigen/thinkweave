import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import History from '../History';

// Ant Design requires window.matchMedia in jsdom
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

const { listTasksMock, batchDeleteTasksMock } = vi.hoisted(() => ({
  listTasksMock: vi.fn(),
  batchDeleteTasksMock: vi.fn(),
}));

vi.mock('../../api/tasks', () => ({
  listTasks: listTasksMock,
  batchDeleteTasks: batchDeleteTasksMock,
  getTask: vi.fn(),
  pauseTask: vi.fn(),
  resumeTask: vi.fn(),
  skipTaskNode: vi.fn(),
  retryTaskNode: vi.fn(),
}));

const MOCK_TASKS = [
  {
    id: 'task-1',
    title: '量子计算技术报告',
    mode: 'report',
    status: 'completed',
    fsm_state: 'done',
    word_count: 8500,
    depth: 'standard',
    target_words: 10000,
    created_at: '2026-03-26T10:00:00Z',
    finished_at: '2026-03-26T10:30:00Z',
  },
  {
    id: 'task-2',
    title: '小说草稿第一章',
    mode: 'novel',
    status: 'running',
    fsm_state: 'writing',
    word_count: 0,
    depth: 'quick',
    target_words: 3000,
    created_at: '2026-03-26T11:00:00Z',
    finished_at: null,
  },
];

function renderHistory() {
  return render(
    <MemoryRouter>
      <History />
    </MemoryRouter>
  );
}

describe('History page', () => {
  beforeEach(() => {
    listTasksMock.mockReset();
    batchDeleteTasksMock.mockReset();
    listTasksMock.mockResolvedValue({ items: MOCK_TASKS, total: 2 });
  });

  it('renders page title', async () => {
    renderHistory();
    expect(screen.getByText('历史任务')).toBeTruthy();
  });

  it('fetches and displays tasks on mount', async () => {
    renderHistory();
    await waitFor(() => {
      expect(listTasksMock).toHaveBeenCalledOnce();
    });
    await waitFor(() => {
      expect(screen.getByText('量子计算技术报告')).toBeTruthy();
    });
  });

  it('displays correct total count', async () => {
    renderHistory();
    await waitFor(() => {
      expect(screen.getByText(/共 2 条记录/)).toBeTruthy();
    });
  });

  it('shows status tags', async () => {
    renderHistory();
    await waitFor(() => {
      expect(screen.getByText('已完成')).toBeTruthy();
      expect(screen.getByText('执行中')).toBeTruthy();
    });
  });

  it('shows mode tags', async () => {
    renderHistory();
    await waitFor(() => {
      expect(screen.getByText('技术报告')).toBeTruthy();
      expect(screen.getByText('小说')).toBeTruthy();
    });
  });

  it('shows word count formatted', async () => {
    renderHistory();
    await waitFor(() => {
      expect(screen.getByText('8.5k')).toBeTruthy();
    });
  });

  it('calls listTasks with search param on search button click', async () => {
    renderHistory();
    await waitFor(() => expect(listTasksMock).toHaveBeenCalledOnce());

    const input = screen.getByPlaceholderText('搜索任务标题…');
    fireEvent.change(input, { target: { value: '量子' } });
    fireEvent.click(screen.getByRole('button', { name: /搜索/ }));

    await waitFor(() => {
      expect(listTasksMock).toHaveBeenCalledWith(
        expect.objectContaining({ search: '量子' })
      );
    });
  });

  it('shows empty state when no tasks', async () => {
    listTasksMock.mockResolvedValue({ items: [], total: 0 });
    renderHistory();
    await waitFor(() => {
      expect(screen.getByText('暂无历史任务')).toBeTruthy();
    });
  });

  it('calls batchDeleteTasks with selected ids', async () => {
    batchDeleteTasksMock.mockResolvedValue({ deleted_count: 1 });
    renderHistory();
    await waitFor(() => screen.getByText('量子计算技术报告'));

    // 选中第一行
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]); // index 0 = select-all

    await waitFor(() => {
      expect(screen.getByText(/删除 \(1\)/)).toBeTruthy();
    });
  });
});
