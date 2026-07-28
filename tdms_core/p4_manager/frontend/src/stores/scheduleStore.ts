import { defineStore } from 'pinia';
import axios from 'axios';

export interface ScheduleJob {
  job_id: string;
  name: string;
  next_run_time: string | null;
  trigger: string;
  is_paused: boolean;
}

export const useScheduleStore = defineStore('schedule', {
  state: () => ({
    krSchedules: [] as ScheduleJob[],
    usSchedules: [] as ScheduleJob[],
    isLoading: false,
    errorMessage: '',
  }),
  actions: {
    async fetchSchedules(market: 'kr' | 'us') {
      this.isLoading = true;
      this.errorMessage = '';
      try {
        const response = await axios.get<ScheduleJob[]>(`/api/mgr/schedules/${market}`);
        if (market === 'kr') {
          this.krSchedules = response.data;
        } else {
          this.usSchedules = response.data;
        }
      } catch (error: any) {
        this.errorMessage = error.response?.data?.detail || `Failed to fetch ${market} schedules.`;
      } finally {
        this.isLoading = false;
      }
    },
    
    async rescheduleJob(market: 'kr' | 'us', jobId: string, hour: number, minute: number, dayOfWeek?: string) {
      this.isLoading = true;
      this.errorMessage = '';
      try {
        const params: any = { hour, minute };
        if (dayOfWeek) {
          params.day_of_week = dayOfWeek;
        }
        await axios.put(`/api/mgr/schedules/${market}/${jobId}`, null, {
          params
        });
        await this.fetchSchedules(market);
      } catch (error: any) {
        this.errorMessage = error.response?.data?.detail || 'Failed to reschedule task.';
        throw error;
      } finally {
        this.isLoading = false;
      }
    },

    async reloadSchedules(market: 'kr' | 'us') {
      this.isLoading = true;
      this.errorMessage = '';
      try {
        await axios.post(`/api/mgr/schedules/${market}/reload`);
        await this.fetchSchedules(market);
      } catch (error: any) {
        this.errorMessage = error.response?.data?.detail || 'Failed to reload schedule from .env';
        throw error;
      } finally {
        this.isLoading = false;
      }
    },
    
    async toggleJob(market: 'kr' | 'us', jobId: string, action: 'pause' | 'resume') {
      this.isLoading = true;
      this.errorMessage = '';
      try {
        await axios.post(`/api/mgr/schedules/${market}/${jobId}/toggle`, null, {
          params: { action }
        });
        await this.fetchSchedules(market);
      } catch (error: any) {
        this.errorMessage = error.response?.data?.detail || `Failed to ${action} task.`;
        throw error;
      } finally {
        this.isLoading = false;
      }
    }
  }
});
