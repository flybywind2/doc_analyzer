"""
Statistics router
"""
from typing import Dict, Any, List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.auth import get_current_user
from app.services.statistics import statistics_service
from app.models.user import User

router = APIRouter(prefix="/statistics", tags=["Statistics"])


@router.get("/summary", response_model=Dict[str, Any])
async def get_summary_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get summary statistics
    
    Admins see all data
    Reviewers see only their department's data
    """
    department_id = None if current_user.role == "admin" else current_user.department_id
    
    return statistics_service.get_summary_stats(db, department_id)


@router.get("/by-department", response_model=List[Dict[str, Any]])
async def get_department_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get statistics by department (admin only)
    """
    if current_user.role != "admin":
        # Return only current user's department stats
        stats = statistics_service.get_department_stats(db)
        return [s for s in stats if s["department_id"] == current_user.department_id]
    
    return statistics_service.get_department_stats(db)


@router.get("/by-category", response_model=List[Dict[str, Any]])
async def get_category_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get statistics by AI category
    
    Admins see all data
    Reviewers see only their department's data
    """
    department_id = None if current_user.role == "admin" else current_user.department_id
    
    return statistics_service.get_category_stats(db, department_id)


@router.get("/grade-distribution", response_model=Dict[str, Any])
async def get_grade_distribution_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get grade distribution statistics
    
    Admins see all data
    Reviewers see only their department's data
    """
    department_id = None if current_user.role == "admin" else current_user.department_id
    
    return statistics_service.get_grade_distribution(db, department_id)


@router.get("/tech-skills", response_model=Dict[str, Any])
async def get_tech_skill_statistics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get technology skill statistics
    
    Admins see all data
    Reviewers see only their department's data
    """
    department_id = None if current_user.role == "admin" else current_user.department_id
    
    return statistics_service.get_tech_skill_stats(db, department_id)
