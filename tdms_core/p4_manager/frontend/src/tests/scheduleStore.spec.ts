import { describe, it, expect, beforeEach, vi } from 'vitest';
import { setActivePinia, createPinia } from 'pinia';
import { useScheduleStore } from '../stores/scheduleStore';
import axios from 'axios';

vi.mock('axios');

describe('scheduleStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it('fetchSchedules - 성공 시 올바르게 스토어 상태 갱신', async () => {
    const mockData = [
      { job_id: 'daily_update', name: 'daily_update', next_run_time: '2026-06-09T17:00:00', trigger: 'cron', is_paused: false }
    ];
    vi.mocked(axios.get).mockResolvedValueOnce({ data: mockData });

    const store = useScheduleStore();
    await store.fetchSchedules('kr');

    expect(store.krSchedules).toEqual(mockData);
    expect(store.isLoading).toBe(false);
    expect(axios.get).toHaveBeenCalledWith('/api/mgr/schedules/kr');
  });

  it('fetchSchedules - 실패 시 에러메시지 기록', async () => {
    vi.mocked(axios.get).mockRejectedValueOnce({
      response: { data: { detail: 'Internal Server Error' } }
    });

    const store = useScheduleStore();
    await store.fetchSchedules('us');

    expect(store.usSchedules).toEqual([]);
    expect(store.errorMessage).toBe('Internal Server Error');
  });

  it('rescheduleJob - 시간 갱신 요청 성공 후 재조회', async () => {
    vi.mocked(axios.put).mockResolvedValueOnce({ data: { status: 'SUCCESS' } });
    vi.mocked(axios.get).mockResolvedValueOnce({ data: [] });

    const store = useScheduleStore();
    await store.rescheduleJob('us', 'daily_collection_job', 10, 45);

    expect(axios.put).toHaveBeenCalledWith('/api/mgr/schedules/us/daily_collection_job', null, {
      params: { hour: 10, minute: 45 }
    });
    expect(axios.get).toHaveBeenCalledWith('/api/mgr/schedules/us');
  });

  it('toggleJob - 토글 상태 성공 및 재조회', async () => {
    vi.mocked(axios.post).mockResolvedValueOnce({ data: { status: 'PAUSED' } });
    vi.mocked(axios.get).mockResolvedValueOnce({ data: [] });

    const store = useScheduleStore();
    await store.toggleJob('kr', 'daily_update', 'pause');

    expect(axios.post).toHaveBeenCalledWith('/api/mgr/schedules/kr/daily_update/toggle', null, {
      params: { action: 'pause' }
    });
  });
});
