// src/types/data.ts

// API 조회 파라미터 타입
export interface DataPreviewParams {
  limit: number;
  offset: number;
  stk_cd?: string;
  start_date?: string;
  end_date?: string;
  quarter?: string;
}

// DB 테이블의 동적 행 데이터 (Key-Value 구조)
// 컬럼명이 무엇이든 될 수 있고, 값도 다양하므로 unknown 사용
export type TableRow = Record<string, unknown>;