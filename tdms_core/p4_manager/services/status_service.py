# tdms_core/p4_manager/services/status_service.py
import asyncio
import logging
import httpx
from typing import Dict, Any, Optional
from tdms_core.p4_manager.config import settings

logger = logging.getLogger("p4_manager.status_service")

class StatusService:
    def __init__(self):
        self._cache: Dict[str, Any] = {
            "kr": {
                "status": "OFFLINE",
                "freshness": None,
                "tasks": None
            },
            "us": {
                "status": "OFFLINE",
                "freshness": None,
                "tasks": None
            }
        }

    def get_status(self) -> Dict[str, Any]:
        return self._cache

    async def fetch_and_cache_status(self):
        async with httpx.AsyncClient(timeout=2.0) as client:
            kr_task = self._fetch_kr_status(client)
            us_task = self._fetch_us_status(client)
            
            kr_result, us_result = await asyncio.gather(kr_task, us_task)
            
            self._cache["kr"] = kr_result
            self._cache["us"] = us_result

    async def _fetch_kr_status(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        try:
            freshness_url = f"{settings.P2_KDMS_URL}/api/health/freshness"
            tasks_url = f"{settings.P2_KDMS_URL}/api/v1/admin/tasks/status"
            
            freshness_resp, tasks_resp = await asyncio.gather(
                client.get(freshness_url),
                client.get(tasks_url)
            )
            
            if freshness_resp.status_code != 200 or tasks_resp.status_code != 200:
                raise ValueError(f"Non-200 status code: freshness={freshness_resp.status_code}, tasks={tasks_resp.status_code}")
                
            p2_freshness = freshness_resp.json()
            p2_tasks = tasks_resp.json()
            
            freshness_data = {
                "status": p2_freshness.get("status", "RED"),
                "latest_trading_date": p2_freshness.get("latest_trading_date"),
                "daily_coverage_ratio": p2_freshness.get("daily_coverage_ratio", 0.0),
                "is_daily_fresh": p2_freshness.get("is_daily_fresh", False)
            }
            
            daily_update = p2_tasks.get("daily_update", {})
            is_running = any(job.get("is_running", False) for job in p2_tasks.values())
            raw_status = daily_update.get("last_status", "none")
            last_status = raw_status.lower() if raw_status else "none"
            last_run_time = daily_update.get("last_run_time")
            
            tasks_data = {
                "is_running": is_running,
                "last_run_time": last_run_time,
                "last_status": last_status
            }
            
            return {
                "status": "ONLINE",
                "freshness": freshness_data,
                "tasks": tasks_data
            }
            
        except Exception as e:
            logger.error(f"Error fetching KR status: {e}")
            return {
                "status": "OFFLINE",
                "freshness": None,
                "tasks": None
            }

    async def _fetch_us_status(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        try:
            freshness_url = f"{settings.P3_USDMS_URL}/api/health/freshness"
            tasks_url = f"{settings.P3_USDMS_URL}/api/admin/tasks/status"
            
            freshness_resp, tasks_resp = await asyncio.gather(
                client.get(freshness_url),
                client.get(tasks_url)
            )
            
            if freshness_resp.status_code != 200 or tasks_resp.status_code != 200:
                raise ValueError(f"Non-200 status code: freshness={freshness_resp.status_code}, tasks={tasks_resp.status_code}")
                
            p3_freshness = freshness_resp.json()
            p3_tasks = tasks_resp.json()
            
            freshness_data = {
                "status": p3_freshness.get("status", "RED"),
                "latest_trading_date": p3_freshness.get("latest_trading_date"),
                "daily_coverage_ratio": p3_freshness.get("daily_coverage_ratio", 0.0),
                "is_daily_fresh": p3_freshness.get("is_daily_fresh", False)
            }
            
            is_running = any(job.get("is_running", False) for job in p3_tasks)
            last_run_time = None
            last_status = "none"
            
            if p3_tasks:
                latest_job = p3_tasks[0]
                last_run_time = latest_job.get("end_time") or latest_job.get("start_time")
                raw_status = latest_job.get("status", "none")
                if raw_status == "SUCCESS":
                    last_status = "success"
                elif raw_status == "FAILED":
                    last_status = "failed"
                else:
                    last_status = raw_status.lower() if raw_status else "none"
            
            tasks_data = {
                "is_running": is_running,
                "last_run_time": last_run_time,
                "last_status": last_status
            }
            
            return {
                "status": "ONLINE",
                "freshness": freshness_data,
                "tasks": tasks_data
            }
            
        except Exception as e:
            logger.error(f"Error fetching US status: {e}")
            return {
                "status": "OFFLINE",
                "freshness": None,
                "tasks": None
            }

status_service = StatusService()
