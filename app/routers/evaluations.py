"""
Evaluations router
"""
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.evaluation import (
    AIEvaluationRequest, AIEvaluationResponse,
    EvaluationHistoryResponse, EvaluationCriteriaResponse,
    EvaluationCriteriaCreate, EvaluationCriteriaUpdate
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

    # Check if there are applications to evaluate
    if not applications:
        return AIEvaluationResponse(
            success_count=0,
            fail_count=0,
            failed_ids=[],
            error_messages=["No applications found to evaluate. All applications may have been already evaluated. Use force_re_evaluate=true to re-evaluate."]
        )

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

    total_count = len(applications)
    print(f"\n{'='*80}")
    print(f"🤖 AI 평가 시작: 총 {total_count}개 지원서")
    print(f"{'='*80}\n")

    for idx, app in enumerate(applications, 1):
        try:
            print(f"[{idx}/{total_count}] 평가 중: Application ID {app.id} - {app.subject or 'N/A'}")

            # Classify AI technology
            ai_classifier.classify_and_update(db, app, categories)

            # Evaluate with LLM
            success = llm_evaluator.evaluate_application(db, app, criteria_list)

            if success:
                success_count += 1
                print(f"  ✅ 평가 완료")
            else:
                fail_count += 1
                failed_ids.append(app.id)
                error_messages.append(f"Failed to evaluate application {app.id}")
                print(f"  ❌ 평가 실패")

        except Exception as e:
            fail_count += 1
            failed_ids.append(app.id)
            error_messages.append(f"Error evaluating application {app.id}: {str(e)}")
            print(f"  ❌ 오류 발생: {str(e)}")

    print(f"\n{'='*80}")
    print(f"✅ AI 평가 완료")
    print(f"  총 지원서: {total_count}")
    print(f"  성공: {success_count}")
    print(f"  실패: {fail_count}")
    print(f"{'='*80}\n")

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
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List evaluation criteria
    """
    query = db.query(EvaluationCriteria)

    if not include_inactive:
        query = query.filter(EvaluationCriteria.is_active == True)

    if batch_id:
        query = query.filter(EvaluationCriteria.batch_id == batch_id)
    else:
        query = query.filter(EvaluationCriteria.batch_id.is_(None))

    criteria = query.order_by(EvaluationCriteria.display_order).all()

    return [EvaluationCriteriaResponse.model_validate(c) for c in criteria]


@router.post("/criteria", response_model=EvaluationCriteriaResponse)
async def create_evaluation_criteria(
    criteria_data: EvaluationCriteriaCreate,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Create new evaluation criteria (Admin only)
    """
    criteria = EvaluationCriteria(**criteria_data.model_dump())
    db.add(criteria)

    try:
        db.commit()
        db.refresh(criteria)
        return EvaluationCriteriaResponse.model_validate(criteria)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create criteria: {str(e)}"
        )


@router.put("/criteria/{criteria_id}", response_model=EvaluationCriteriaResponse)
async def update_evaluation_criteria(
    criteria_id: int,
    criteria_data: EvaluationCriteriaUpdate,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Update evaluation criteria (Admin only)
    """
    criteria = db.query(EvaluationCriteria).filter(
        EvaluationCriteria.id == criteria_id
    ).first()

    if not criteria:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Criteria not found"
        )

    # Update fields
    update_data = criteria_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(criteria, field, value)

    criteria.updated_at = datetime.utcnow()

    try:
        db.commit()
        db.refresh(criteria)
        return EvaluationCriteriaResponse.model_validate(criteria)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update criteria: {str(e)}"
        )


@router.delete("/criteria/{criteria_id}")
async def delete_evaluation_criteria(
    criteria_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Delete evaluation criteria (Admin only)
    Actually sets is_active to False
    """
    criteria = db.query(EvaluationCriteria).filter(
        EvaluationCriteria.id == criteria_id
    ).first()

    if not criteria:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Criteria not found"
        )

    # Soft delete
    criteria.is_active = False
    criteria.updated_at = datetime.utcnow()

    try:
        db.commit()
        return {"message": "Criteria deactivated successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete criteria: {str(e)}"
        )
