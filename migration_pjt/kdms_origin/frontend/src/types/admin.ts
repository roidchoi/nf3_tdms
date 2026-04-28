// src/types/admin.ts

// 개별 태스크 상태 (PRD 4.1.2 job_statuses 구조 매핑)
export interface TaskStatus {
  is_running: boolean;
  phase: string;       // 예: "2/4"
  phase_name: string;  // 예: "팩터 및 시세 동기화"
  progress: number;    // 0 ~ 100
  start_time?: string;
  end_time?: string;
  duration?: string;
  last_log?: string;   // "tqdm" 스타일 로그 또는 마지막 메시지
  last_status?: string; // "success", "failure", "none"
  error?: string;
  stocks_processed?: number;
  total_stocks?: number;
}

// 전체 태스크 맵 (daily_update, financial_update 등)
export interface JobStatuses {
  [key: string]: TaskStatus;
}

// 스케줄 정보 (GET /admin/schedules 응답)
export interface ScheduleItem {
  id: string;
  task_id: string;
  trigger: string;
  next_run: string | null;
  is_paused: boolean;
}

// [신규] Cron 스케줄 설정 타입 (any 대체)
export interface CronConfig {
  day_of_week?: string; // 예: "mon-fri", "sun"
  hour?: number | string;
  minute?: number | string;
}

// [신규] 스케줄 생성 요청 페이로드
export interface ScheduleCreatePayload {
  task_id: string;
  trigger: string; // "cron"
  config: CronConfig;
}