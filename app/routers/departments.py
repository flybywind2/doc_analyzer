"""
Departments management router
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.evaluation import DepartmentCreate, DepartmentUpdate, DepartmentResponse
from app.services.auth import get_current_active_admin
from app.models.user import User
from app.models.department import Department

router = APIRouter(prefix="/departments", tags=["Departments"])


@router.get("", response_model=List[DepartmentResponse])
async def list_departments(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    List all departments
    """
    departments = db.query(Department).offset(skip).limit(limit).all()
    return [DepartmentResponse.model_validate(dept) for dept in departments]


@router.get("/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: int,
    db: Session = Depends(get_db)
):
    """
    Get department by ID
    """
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found"
        )
    return DepartmentResponse.model_validate(dept)


@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
async def create_department(
    dept_data: DepartmentCreate,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Create new department (admin only)
    """
    # Check if name already exists
    existing = db.query(Department).filter(Department.name == dept_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department name already exists"
        )
    
    new_dept = Department(
        name=dept_data.name,
        description=dept_data.description,
        total_employees=dept_data.total_employees
    )
    
    db.add(new_dept)
    db.commit()
    db.refresh(new_dept)
    
    return DepartmentResponse.model_validate(new_dept)


@router.put("/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: int,
    dept_data: DepartmentUpdate,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Update department (admin only)
    """
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found"
        )
    
    # Check if new name already exists
    if dept_data.name and dept_data.name != dept.name:
        existing = db.query(Department).filter(Department.name == dept_data.name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department name already exists"
            )
    
    # Update fields
    update_data = dept_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(dept, field, value)
    
    db.commit()
    db.refresh(dept)
    
    return DepartmentResponse.model_validate(dept)


@router.delete("/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    department_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Delete department (admin only)
    """
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found"
        )
    
    # Check if department has users
    user_count = db.query(User).filter(User.department_id == department_id).count()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete department with {user_count} users"
        )
    
    db.delete(dept)
    db.commit()
    
    return None
