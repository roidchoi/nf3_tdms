import { describe, it, expect, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import ScheduleModal from '../components/dashboard/ScheduleModal.vue';

describe('ScheduleModal.vue', () => {
  const defaultProps = {
    isOpen: true,
    market: 'us' as const,
    job: {
      job_id: 'daily_collection_job',
      name: 'daily_collection_job',
      next_run_time: '2026-06-09T17:00:00Z',
      trigger: 'cron'
    }
  };

  it('미국 마켓(us)인 경우 KST 입력 시 EST 변환 문구를 표출해야 한다', () => {
    const wrapper = mount(ScheduleModal, {
      props: defaultProps
    });
    
    // selectedHour 기본값이 17이면, convertedEstTime은 17-13 = 4가 되므로 "04:00 EST" 형태가 표시되어야 함
    expect(wrapper.text()).toContain('EST');
    expect(wrapper.find('.converted-time').text()).toContain('04:00 EST');
  });

  it('수집 가동 시간대(장중)일 경우 경고창을 표시하고 "변경승인" 입력 전까지 적용 버튼을 비활성화한다', async () => {
    // 한국 시간 10시는 한국 시장의 장중 시간 (09:00 ~ 16:00)
    // Date mock을 활용해 장중으로 세팅
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 5, 9, 10, 0, 0)); // KST 10:00

    const wrapper = mount(ScheduleModal, {
      props: {
        ...defaultProps,
        market: 'kr'
      }
    });

    expect(wrapper.find('.danger-warning').exists()).toBe(true);
    
    const confirmBtn = wrapper.find('.btn-confirm');
    expect(confirmBtn.attributes('disabled')).toBeDefined();

    // 잘못된 단어 입력 시 비활성화 유지
    const input = wrapper.find('.safety-input');
    await input.setValue('확인');
    expect(confirmBtn.attributes('disabled')).toBeDefined();

    // 올바른 단어 입력 시 활성화
    await input.setValue('변경승인');
    expect(confirmBtn.attributes('disabled')).toBeUndefined();

    vi.useRealTimers();
  });
});
