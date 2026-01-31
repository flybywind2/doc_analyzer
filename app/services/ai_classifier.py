"""
AI Classifier Service
"""
import json
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.application import Application
from app.models.category import AICategory


class AIClassifier:
    """AI Technology Classifier"""
    
    def classify_application(
        self, 
        db: Session, 
        application: Application,
        categories: List[AICategory] = None
    ) -> List[Dict[str, Any]]:
        """
        Classify application into AI technology categories
        
        Args:
            db: Database session
            application: Application to classify
            categories: List of AI categories (optional, will fetch if None)
            
        Returns:
            List of categories with priority and confidence
        """
        # Get categories if not provided
        if categories is None:
            categories = db.query(AICategory).filter(
                AICategory.is_active == True
            ).order_by(AICategory.display_order).all()
        
        if not categories:
            return []
        
        # Combine all text from application
        text_parts = [
            application.subject or "",
            application.current_work or "",
            application.pain_point or "",
            application.improvement_idea or "",
            application.expected_effect or "",
            application.hope or ""
        ]
        combined_text = " ".join(text_parts).lower()
        
        # Score each category based on keyword matching
        category_scores = []
        for category in categories:
            score = 0
            keywords = []
            
            # Parse keywords from JSON string
            if category.keywords:
                try:
                    keywords = json.loads(category.keywords)
                except:
                    keywords = []
            
            # Count keyword matches
            for keyword in keywords:
                if keyword.lower() in combined_text:
                    score += 1
            
            if score > 0:
                category_scores.append({
                    "category": category.name,
                    "score": score,
                    "keywords_matched": score
                })
        
        # Sort by score and assign priority
        category_scores.sort(key=lambda x: x["score"], reverse=True)
        
        # Build result with priority
        result = []
        for i, cat_score in enumerate(category_scores[:3], 1):  # Top 3
            # Calculate confidence (normalized score)
            max_score = category_scores[0]["score"] if category_scores else 1
            confidence = cat_score["score"] / max_score if max_score > 0 else 0
            
            result.append({
                "category": cat_score["category"],
                "priority": i,
                "confidence": round(confidence, 2),
                "keywords_matched": cat_score["keywords_matched"]
            })
        
        return result
    
    def classify_and_update(
        self, 
        db: Session, 
        application: Application,
        categories: List[AICategory] = None
    ) -> bool:
        """
        Classify application and update database
        
        Args:
            db: Database session
            application: Application to classify
            categories: List of AI categories (optional)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            classification = self.classify_application(db, application, categories)
            
            if classification:
                application.ai_categories = classification
                application.ai_category_primary = classification[0]["category"]
                db.commit()
                print(f"✅ Classified application {application.id}: {application.ai_category_primary}")
                return True
            else:
                # Fallback: 키워드 매칭이 없는 경우, "데이터분석"을 기본으로 설정
                print(f"⚠️  No categories matched for application {application.id}")
                print(f"   ℹ️  Setting default category '데이터분석' as fallback")
                
                # 기본 카테고리 설정
                application.ai_categories = [{
                    "category": "데이터분석",
                    "priority": 1,
                    "confidence": 0.0,
                    "keywords_matched": 0,
                    "note": "No keyword matches - default category assigned"
                }]
                application.ai_category_primary = "데이터분석"
                db.commit()
                return True
                
        except Exception as e:
            print(f"❌ Error classifying application {application.id}: {e}")
            db.rollback()
            return False


# Singleton instance
ai_classifier = AIClassifier()
