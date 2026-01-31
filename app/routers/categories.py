"""
AI Categories management router
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.evaluation import AICategoryCreate, AICategoryUpdate, AICategoryResponse
from app.services.auth import get_current_active_admin
from app.models.user import User
from app.models.category import AICategory

router = APIRouter(prefix="/categories", tags=["AI Categories"])


@router.get("", response_model=List[AICategoryResponse])
async def list_categories(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    List all AI categories
    """
    categories = db.query(AICategory).order_by(AICategory.display_order).offset(skip).limit(limit).all()
    return [AICategoryResponse.model_validate(cat) for cat in categories]


@router.get("/{category_id}", response_model=AICategoryResponse)
async def get_category(
    category_id: int,
    db: Session = Depends(get_db)
):
    """
    Get category by ID
    """
    cat = db.query(AICategory).filter(AICategory.id == category_id).first()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )
    return AICategoryResponse.model_validate(cat)


@router.post("", response_model=AICategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    cat_data: AICategoryCreate,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Create new AI category (admin only)
    """
    # Check if name already exists
    existing = db.query(AICategory).filter(AICategory.name == cat_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category name already exists"
        )
    
    new_cat = AICategory(
        name=cat_data.name,
        description=cat_data.description,
        keywords=cat_data.keywords,
        display_order=cat_data.display_order,
        is_active=cat_data.is_active
    )
    
    db.add(new_cat)
    db.commit()
    db.refresh(new_cat)
    
    return AICategoryResponse.model_validate(new_cat)


@router.put("/{category_id}", response_model=AICategoryResponse)
async def update_category(
    category_id: int,
    cat_data: AICategoryUpdate,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Update AI category (admin only)
    """
    cat = db.query(AICategory).filter(AICategory.id == category_id).first()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )
    
    # Check if new name already exists
    if cat_data.name and cat_data.name != cat.name:
        existing = db.query(AICategory).filter(AICategory.name == cat_data.name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Category name already exists"
            )
    
    # Update fields
    update_data = cat_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(cat, field, value)
    
    db.commit()
    db.refresh(cat)
    
    return AICategoryResponse.model_validate(cat)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    current_user: User = Depends(get_current_active_admin),
    db: Session = Depends(get_db)
):
    """
    Delete AI category (admin only)
    """
    cat = db.query(AICategory).filter(AICategory.id == category_id).first()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found"
        )
    
    db.delete(cat)
    db.commit()
    
    return None
