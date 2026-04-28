export interface HealthFreshness {
  last_daily_dt: string | null;
  last_minute_dt_tm: string | null;
  daily_lag_days: number | null;
  is_daily_fresh: boolean;
}

export interface HealthFinancials {
  latest_stac_yymm: string | null;
  distinct_stocks_count: number;
  latest_retrieved_at: string | null;
}

export interface HealthFactors {
  total_events_count: number;
  distinct_stocks_count: number;
  latest_event_dt: string | null;
}

export interface GapResult {
  market: string;
  target_quarter: string;
  target_stocks_count: number;
  total_trading_days: number;
  missing_days_count: number;
  missing_days: string[];
}

export interface GapCheckResponse {
  analysis_period: {
    start_date: string;
    end_date: string;
  };
  results: GapResult[];
}

export interface SystemMilestone {
  milestone_name: string;
  milestone_date: string; // YYYY-MM-DD
  description: string;
  updated_at: string;     // ISO datetime
}

export interface SystemMilestonePayload {
  milestone_name: string;
  milestone_date: string;
  description: string;
}