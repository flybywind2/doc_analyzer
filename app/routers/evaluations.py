"""
Evaluations router
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.evaluation import (
    AIEvaluationRequest, AIEvaluationResponse,
    EvaluationHistoryResponse, EvaluationCriteriaResponse
)
from app.services.auth import get_current_active_admin, get_current_user
from app.services.llm_evaluator import llm_evaluator
from app.services.ai_classifier import ai_classifier
from app.models.user import User
from app.models.application import Application
from app.models.evaluation import EvaluationHistory, EvaluationCriteria

router = APIRouter(prefix="/evaluations", tags=["Evaluations"])


@router.post("/run-ai", response_model=AIEvaluationResponse)
async def run_ai_evaluation(
    request: AIEvaluationRequest,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Run AI evaluation on applications (admin only)
    
    If application_ids is provided, evaluate those applications
    Otherwise, evaluate all pending applications
    """
    # Get applications to evaluate
    if request.application_ids:
        query = db.query(Application).filter(Application.id.in_(request.application_ids))
    else:
        if request.force_re_evaluate:
            query = db.query(Application)
        else:
            query = db.query(Application).filter(Application.ai_grade.is_(None))
    
    applications = query.all()
    
    # Get evaluation criteria
    criteria_list = db.query(EvaluationCriteria).filter(
        EvaluationCriteria.is_active == True
    ).order_by(EvaluationCriteria.display_order).all()
    
    # Get AI categories
    from app.models.category import AICategory
    categories = db.query(AICategory).filter(AICategory.is_active == True).all()
    
    # Evaluate each application
    success_count = 0
    fail_count = 0
    failed_ids = []
    error_messages = []
    
    for app in applications:
        try:
            # Classify AI technology
            ai_classifier.classify_and_update(db, app, categories)
            
            # Evaluate with LLM
            success = llm_evaluator.evaluate_application(db, app, criteria_list)
            
            if success:
                success_count += 1
            else:
                fail_count += 1
                failed_ids.append(app.id)
                error_messages.append(f"Failed to evaluate application {app.id}")
                
        except Exception as e:
            fail_count += 1
            failed_ids.append(app.id)
            error_messages.append(f"Error evaluating application {app.id}: {str(e)}")
    
    return AIEvaluationResponse(
        success_count=success_count,
        fail_count=fail_count,
        failed_ids=failed_ids,
        error_messages=error_messages
    )


@router.post("/{application_id}/re-evaluate")
async def re_evaluate_application(
    application_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Re-evaluate single application with AI (admin only)
    """
    app = db.query(Application).filter(Application.id == application_id).first()
    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found"
        )
    
    # Get evaluation criteria
    criteria_list = db.query(EvaluationCriteria).filter(
        EvaluationCriteria.is_active == True
    ).order_by(EvaluationCriteria.display_order).all()
    
    # Get AI categories
    from app.models.category import AICategory
    categories = db.query(AICategory).filter(AICategory.is_active == True).all()
    
    try:
        # Classify AI technology
        ai_classifier.classify_and_update(db, app, categories)
        
        # Evaluate with LLM
        success = llm_evaluator.evaluate_application(db, app, criteria_list)
        
        if success:
            return {"message": "Re-evaluation completed successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Re-evaluation failed"
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Re-evaluation error: {str(e)}"
        )


@router.get("/{application_id}/history", response_model=List[EvaluationHistoryResponse])
async def get_evaluation_history(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get evaluation history for application
    """
    # Check if application exists and user has permission
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
    
    # Get history
    histories = db.query(EvaluationHistory).filter(
        EvaluationHistory.application_id == application_id
    ).order_by(EvaluationHistory.created_at.desc()).all()
    
    result = []
    for history in histories:
        history_data = EvaluationHistoryResponse.model_validate(history)
        if history.evaluator:
            history_data.evaluator_name = history.evaluator.name
        result.append(history_data)
    
    return result


@router.get("/criteria", response_model=List[EvaluationCriteriaResponse])
async def list_evaluation_criteria(
    batch_id: str = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List evaluation criteria
    """
    query = db.query(EvaluationCriteria).filter(EvaluationCriteria.is_active == True)
    
    if batch_id:
        query = query.filter(EvaluationCriteria.batch_id == batch_id)
    else:
        query = query.filter(EvaluationCriteria.batch_id.is_(None))
    
    criteria = query.order_by(EvaluationCriteria.display_order).all()
    
    return [EvaluationCriteriaResponse.model_validate(c) for c in criteria]
