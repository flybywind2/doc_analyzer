"""
Web pages router
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.services.auth import get_current_user
from app.models.user import User

router = APIRouter(tags=["Web Pages"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Dashboard page"""
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "user": current_user}
    )


@router.get("/applications", response_class=HTMLResponse)
async def applications_list_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Applications list page"""
    return templates.TemplateResponse(
        "applications/list.html",
        {"request": request, "user": current_user}
    )


@router.get("/applications/{application_id}", response_class=HTMLResponse)
async def application_detail_page(
    application_id: int,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Application detail page"""
    return templates.TemplateResponse(
        "applications/detail.html",
        {"request": request, "user": current_user, "application_id": application_id}
    )


@router.get("/auth/change-password", response_class=HTMLResponse)
async def change_password_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Change password page"""
    return templates.TemplateResponse(
        "change_password.html",
        {"request": request, "user": current_user}
    )
