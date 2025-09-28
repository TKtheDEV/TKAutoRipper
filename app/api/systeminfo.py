from fastapi import APIRouter, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from app.core.auth import verify_web_auth
from app.core.systeminfo import get_system_info

router = APIRouter()

@router.get("/api/system-info", dependencies=[Depends(verify_web_auth)])
def system_info():
    return get_system_info()
