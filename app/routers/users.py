"""
Users management router
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.auth import get_current_active_admin, get_password_hash
from app.models.user import User
from app.models.department import Department

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserResponse])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    List all users (admin only)
    """
    users = db.query(User).offset(skip).limit(limit).all()

    result = []
    for user in users:
        user_data = UserResponse.model_validate(user)

        # Legacy single department
        if user.department:
            user_data.department_name = user.department.name

        # Multiple departments
        if user.departments:
            user_data.department_ids = [dept.id for dept in user.departments]
            user_data.department_names = [dept.name for dept in user.departments]
        else:
            user_data.department_ids = []
            user_data.department_names = []

        result.append(user_data)

    return result


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Get user by ID (admin only)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user_data = UserResponse.model_validate(user)

    # Legacy single department
    if user.department:
        user_data.department_name = user.department.name

    # Multiple departments
    if user.departments:
        user_data.department_ids = [dept.id for dept in user.departments]
        user_data.department_names = [dept.name for dept in user.departments]
    else:
        user_data.department_ids = []
        user_data.department_names = []

    return user_data


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Create new user (admin only)
    """
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    # Check if department exists (legacy single department)
    if user_data.department_id:
        dept = db.query(Department).filter(Department.id == user_data.department_id).first()
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found"
            )

    # Check if departments exist (multiple departments)
    departments = []
    if user_data.department_ids:
        for dept_id in user_data.department_ids:
            dept = db.query(Department).filter(Department.id == dept_id).first()
            if not dept:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Department {dept_id} not found"
                )
            departments.append(dept)

    # Create user with default password if not provided
    password = user_data.password if user_data.password else user_data.username + "123!"
    password_hash = get_password_hash(password)

    new_user = User(
        username=user_data.username,
        password_hash=password_hash,
        name=user_data.name,
        role=user_data.role,
        department_id=user_data.department_id,
        is_active=user_data.is_active,
        is_first_login=True
    )

    db.add(new_user)
    db.flush()  # Get user ID before adding relationships

    # Add multiple departments
    if departments:
        new_user.departments = departments

    db.commit()
    db.refresh(new_user)

    user_response = UserResponse.model_validate(new_user)

    # Legacy single department
    if new_user.department:
        user_response.department_name = new_user.department.name

    # Multiple departments
    if new_user.departments:
        user_response.department_ids = [dept.id for dept in new_user.departments]
        user_response.department_names = [dept.name for dept in new_user.departments]
    else:
        user_response.department_ids = []
        user_response.department_names = []

    return user_response


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Update user (admin only)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Check if department exists (legacy single department)
    if user_data.department_id:
        dept = db.query(Department).filter(Department.id == user_data.department_id).first()
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found"
            )

    # Check if departments exist (multiple departments)
    departments = []
    if user_data.department_ids is not None:
        for dept_id in user_data.department_ids:
            dept = db.query(Department).filter(Department.id == dept_id).first()
            if not dept:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Department {dept_id} not found"
                )
            departments.append(dept)

    # Update fields (excluding department_ids which is handled separately)
    update_data = user_data.model_dump(exclude_unset=True, exclude={'department_ids'})
    for field, value in update_data.items():
        setattr(user, field, value)

    # Update multiple departments if provided
    if user_data.department_ids is not None:
        user.departments = departments

    db.commit()
    db.refresh(user)

    user_response = UserResponse.model_validate(user)

    # Legacy single department
    if user.department:
        user_response.department_name = user.department.name

    # Multiple departments
    if user.departments:
        user_response.department_ids = [dept.id for dept in user.departments]
        user_response.department_names = [dept.name for dept in user.departments]
    else:
        user_response.department_ids = []
        user_response.department_names = []

    return user_response


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Delete user (admin only)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent deleting yourself
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself"
        )
    
    db.delete(user)
    db.commit()
    
    return None
