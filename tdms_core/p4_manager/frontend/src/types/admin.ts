// src/types/admin.ts

export interface TaskStatus {
  is_running: boolean;
  phase?: string;
  phase_name?: string;
  progress?: number;
  start_time?: string;
  end_time?: string;
  duration?: string;
  last_log?: string;
  last_status?: string;
  error?: string;
}

export interface JobStatuses {
  [key: string]: TaskStatus;
}

export interface ScheduleItem {
  id: string;
  task_id: string;
  trigger: string;
  next_run: string | null;
  is_paused: boolean;
}

export interface MarketFreshness {
  status: string;
  latest_trading_date: string | null;
  daily_coverage_ratio: number;
  is_daily_fresh: boolean;
}

export interface MarketTaskSummary {
  is_running: boolean;
  last_run_time: string | null;
  last_status: string;
}

export interface MarketStatus {
  status: 'ONLINE' | 'OFFLINE';
  freshness: MarketFreshness | null;
  tasks: MarketTaskSummary | null;
}

export interface IntegratedStatus {
  kr: MarketStatus;
  us: MarketStatus;
}
