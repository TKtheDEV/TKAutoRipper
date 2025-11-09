# auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from .configmanager import config

security = HTTPBasic()

def verify_web_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = config.get("auth", "username")
    correct_password = config.get("auth", "password")
    if not (
        secrets.compare_digest(credentials.username, correct_username) and
        secrets.compare_digest(credentials.password, correct_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
