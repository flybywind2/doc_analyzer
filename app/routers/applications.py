"""
Applications management router
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
import csv
import io
from app.database import get_db
from app.schemas.application import (
    ApplicationResponse, ApplicationFilter, UserEvaluationSubmit, ConfluenceSyncRequest
)
from app.services.auth import get_current_user, get_current_active_admin
from app.services.confluence_parser import confluence_parser
from app.models.user import User
from app.models.application import Application
from app.models.evaluation import EvaluationHistory
from datetime import datetime

router = APIRouter(prefix="/applications", tags=["Applications"])


@router.get("", response_model=List[ApplicationResponse])
async def list_applications(
    department_id: int = None,
    batch_id: str = None,
    ai_grade: str = None,
    user_grade: str = None,
    ai_category: str = None,
    status_filter: str = None,
    search: str = None,
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List applications with filtering
    
    Reviewers can only see their department's applications
    Admins can see all applications
    """
    query = db.query(Application)
    
    # Apply permission filter
    if current_user.role != "admin":
        if not current_user.department_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no department assigned"
            )
        query = query.filter(Application.department_id == current_user.department_id)
    
    # Apply filters
    if department_id:
        query = query.filter(Application.department_id == department_id)
    if batch_id:
        query = query.filter(Application.batch_id == batch_id)
    if ai_grade:
        query = query.filter(Application.ai_grade == ai_grade)
    if user_grade:
        query = query.filter(Application.user_grade == user_grade)
    if ai_category:
        query = query.filter(Application.ai_category_primary == ai_category)
    if status_filter:
        query = query.filter(Application.status == status_filter)
    if search:
        query = query.filter(
            or_(
                Application.subject.like(f"%{search}%"),
                Application.representative_name.like(f"%{search}%")
            )
        )
    
    # Pagination
    applications = query.order_by(Application.created_at.desc()).offset(skip).limit(limit).all()
    
    # Build response
    result = []
    for app in applications:
        app_data = ApplicationResponse.model_validate(app)
        if app.department:
            app_data.department_name = app.department.name
        if app.evaluator:
            app_data.evaluator_name = app.evaluator.name
        result.append(app_data)
    
    return result


@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get application by ID
    """
    app = db.query(Application).filter(Application.id == application_id).first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Check permission
    if current_user.role != "admin":
        if not current_user.department_id or app.department_id != current_user.department_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No permission to view this application"
            )
    
    app_data = ApplicationResponse.model_validate(app)
    if app.department:
        app_data.department_name = app.department.name
    if app.evaluator:
        app_data.evaluator_name = app.evaluator.name
    
    return app_data


@router.post("/{application_id}/evaluate")
async def submit_user_evaluation(
    application_id: int,
    evaluation: UserEvaluationSubmit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit user evaluation for application
    """
    app = db.query(Application).filter(Application.id == application_id).first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Check permission
    if current_user.role != "admin":
        if not current_user.department_id or app.department_id != current_user.department_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No permission to evaluate this application"
            )
    
    # Update application
    app.user_grade = evaluation.grade
    app.user_comment = evaluation.comment
    app.user_evaluated_by = current_user.id
    app.user_evaluated_at = datetime.utcnow()
    app.status = "user_evaluated"
    
    # Save evaluation history
    history = EvaluationHistory(
        application_id=app.id,
        evaluator_id=current_user.id,
        evaluator_type="USER",
        grade=evaluation.grade,
        summary=evaluation.comment,
        evaluation_detail=None,
        ai_categories=app.ai_categories
    )
    db.add(history)
    
    db.commit()
    
    return {"message": "Evaluation submitted successfully"}


@router.post("/sync")
async def sync_confluence_data(
    sync_request: ConfluenceSyncRequest,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Sync applications from Confluence (admin only)
    """
    result = confluence_parser.sync_applications(
        db=db,
        batch_id=sync_request.batch_id,
        force_update=sync_request.force_update
    )
    
    return {
        "message": "Sync completed",
        "result": result
    }


@router.get("/export/csv")
async def export_applications_csv(
    department_id: int = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export applications to CSV
    
    Reviewers can only export their department's data
    Admins can export all data
    """
    query = db.query(Application)
    
    # Apply permission filter
    if current_user.role != "admin":
        if not current_user.department_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User has no department assigned"
            )
        query = query.filter(Application.department_id == current_user.department_id)
    elif department_id:
        query = query.filter(Application.department_id == department_id)
    
    applications = query.all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        "ID", "과제명", "사업부", "참여인원", "대표자", "Knox ID",
        "AI 카테고리", "AI 등급", "사용자 등급", "상태", "배치ID", "등록일"
    ])
    
    # Data rows
    for app in applications:
        writer.writerow([
            app.id,
            app.subject or "",
            app.division or "",
            app.participant_count or 0,
            app.representative_name or "",
            app.representative_knox_id or "",
            app.ai_category_primary or "",
            app.ai_grade or "",
            app.user_grade or "",
            app.status or "",
            app.batch_id or "",
            app.created_at.strftime("%Y-%m-%d %H:%M:%S") if app.created_at else ""
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=applications_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )
