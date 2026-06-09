# tdms_core/p4_manager/main.py
from fastapi import FastAPI

app = FastAPI(title="P4 Manager Backend")

@app.get("/api/mgr/health")
def health_check():
    """
    p4 백엔드 상태를 반환하는 기본 헬스 체크 엔드포인트
    """
    return {"status": "ok", "service": "p4_backend"}
