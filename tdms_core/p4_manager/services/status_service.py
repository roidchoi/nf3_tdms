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
            
            tasks_data = {}
            for task_id, info in p2_tasks.items():
                raw_status = info.get("last_status", "none")
                last_status = raw_status.lower() if raw_status else "none"
                last_run_time = info.get("end_time") or info.get("start_time") or info.get("last_run_time")
                
                tasks_data[task_id] = {
                    "is_running": info.get("is_running", False),
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
            
            tasks_data = {}
            for info in p3_tasks:
                job_id = info.get("job_id") or info.get("routine")
                if not job_id and info.get("file_name"):
                    fname = info["file_name"]
                    if fname.startswith("daily_routine"):
                        job_id = "daily_routine"
                    elif fname.startswith("weekly_backfill"):
                        job_id = "weekly_backfill"
                        
                if not job_id:
                    continue
                raw_status = info.get("status", "none")
                last_status = raw_status.lower() if raw_status else "none"
                last_run_time = info.get("end_time") or info.get("start_time")
                
                tasks_data[job_id] = {
                    "is_running": info.get("is_running", False),
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

    async def run_task(self, market: str, task_id: str, is_test: bool = True) -> Dict[str, Any]:
        if market not in ["kr", "us"]:
            raise ValueError(f"Invalid market: {market}")

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                if market == "kr":
                    url = f"{settings.P2_KDMS_URL}/api/v1/admin/tasks/{task_id}/run"
                    resp = await client.post(url, json={"test_mode": is_test})
                else:  # us
                    url = f"{settings.P3_USDMS_URL}/api/admin/tasks/{task_id}/run"
                    resp = await client.post(url)
                
                if resp.status_code >= 400:
                    return {
                        "status": "error",
                        "message": f"Target backend returned status code {resp.status_code}",
                        "details": resp.text
                    }
                
                # JSON 응답 안전 파싱
                try:
                    details = resp.json()
                except ValueError:
                    details = resp.text

                return {
                    "status": "success",
                    "message": f"Task {task_id} triggered successfully",
                    "details": details
                }
            except httpx.RequestError as e:
                logger.error(f"Error triggering task on {market} backend: {e}")
                raise e

status_service = StatusService()

