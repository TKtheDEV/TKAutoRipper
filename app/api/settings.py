# app/api/settings.py
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse

from app.core.templates import templates
from app.core.auth import verify_web_auth
from app.core.configmanager import config

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse, dependencies=[Depends(verify_web_auth)])
def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "config": config._config_raw
    })


@router.post("/settings", dependencies=[Depends(verify_web_auth)])
def update_setting(
    section: str = Form(...),
    key: str = Form(...),
    value: str = Form(...)
):
    try:
        meta = config._config_raw[section][key]
        typ = meta.get("type", "string")

        if typ == "boolean":
            value = value.lower() in ("1", "true", "yes")
        elif typ == "integer":
            value = int(value)
        elif typ == "float":
            value = float(value)
        elif typ == "list":
            value = [v.strip() for v in value.split(",")]
        # if type is 'path', 'string', or anything else, keep as str

        config.set(section, key, value)
        config.save()
        return f"<script>showToast('✅ Saved {section}.{key}', 'success')</script>"

    except Exception as e:
        return f"<script>showToast('❌ Error saving {section}.{key}: {e}', 'error')</script>"
