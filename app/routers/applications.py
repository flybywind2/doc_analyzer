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
    ApplicationResponse, ApplicationUpdate, ApplicationFilter, UserEvaluationSubmit, ConfluenceSyncRequest, ConfluenceSingleSyncRequest
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

        # 현재 사용자가 이 지원서를 평가했는지 확인
        user_evaluation = db.query(EvaluationHistory).filter(
            EvaluationHistory.application_id == app.id,
            EvaluationHistory.evaluator_id == current_user.id,
            EvaluationHistory.evaluator_type == 'USER'
        ).first()
        app_data.user_has_evaluated = user_evaluation is not None

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


@router.put("/{application_id}")
async def update_application(
    application_id: int,
    update_data: ApplicationUpdate,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Update application basic information (admin only)
    
    Only administrators can update application data
    """
    app = db.query(Application).filter(Application.id == application_id).first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Update fields if provided
    update_dict = update_data.model_dump(exclude_unset=True)
    
    for field, value in update_dict.items():
        setattr(app, field, value)
    
    app.updated_at = datetime.utcnow()
    
    try:
        db.commit()
        db.refresh(app)
        return {"message": "Application updated successfully", "id": app.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update application: {str(e)}"
        )


@router.post("/{application_id}/evaluate")
async def submit_user_evaluation(
    application_id: int,
    evaluation: UserEvaluationSubmit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit or update user evaluation for application
    Each user can have their own evaluation
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
    
    # Check if user already evaluated this application
    existing_history = db.query(EvaluationHistory).filter(
        EvaluationHistory.application_id == app.id,
        EvaluationHistory.evaluator_id == current_user.id,
        EvaluationHistory.evaluator_type == "USER"
    ).first()
    
    if existing_history:
        # Update existing evaluation
        existing_history.grade = evaluation.grade
        existing_history.summary = evaluation.comment
        existing_history.created_at = datetime.utcnow()
        message = "Evaluation updated successfully"
    else:
        # Create new evaluation
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
        message = "Evaluation submitted successfully"
    
    # Update application status if at least one user evaluated
    app.status = "user_evaluated"
    
    # Update application's latest evaluation info (for backward compatibility)
    app.user_grade = evaluation.grade
    app.user_comment = evaluation.comment
    app.user_evaluated_by = current_user.id
    app.user_evaluated_at = datetime.utcnow()
    
    db.commit()
    
    return {"message": message}


@router.get("/{application_id}/evaluations")
async def get_application_evaluations(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all user evaluations for an application
    Admins can see all evaluations
    Reviewers can only see evaluations from their department
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
    
    # Get all user evaluations
    evaluations = db.query(EvaluationHistory).filter(
        EvaluationHistory.application_id == application_id,
        EvaluationHistory.evaluator_type == "USER"
    ).order_by(EvaluationHistory.created_at.desc()).all()
    
    result = []
    for evaluation in evaluations:
        eval_data = {
            "id": evaluation.id,
            "grade": evaluation.grade,
            "comment": evaluation.summary,
            "evaluator_id": evaluation.evaluator_id,
            "evaluator_name": evaluation.evaluator.name if evaluation.evaluator else None,
            "evaluator_username": evaluation.evaluator.username if evaluation.evaluator else None,
            "created_at": evaluation.created_at.isoformat() if evaluation.created_at else None,
            "is_current_user": evaluation.evaluator_id == current_user.id
        }
        result.append(eval_data)
    
    return result
    
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


@router.post("/sync/single")
async def sync_single_confluence_page(
    sync_request: ConfluenceSingleSyncRequest,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Sync a single application from Confluence by page ID (admin only)
    """
    result = confluence_parser.sync_single_application(
        db=db,
        page_id=sync_request.page_id,
        batch_id=sync_request.batch_id,
        force_update=sync_request.force_update
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"]
        )

    return {
        "message": f"Single page sync {result['action']}",
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
