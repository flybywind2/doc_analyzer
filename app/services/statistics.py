"""
Statistics Service
"""
from typing import Dict, Any, List, Optional
from sqlalchemy import func, case
from sqlalchemy.orm import Session
from app.models.application import Application
from app.models.department import Department
from app.models.category import AICategory


class StatisticsService:
    """Statistics calculation service"""
    
    def get_summary_stats(self, db: Session, department_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get summary statistics
        
        Args:
            db: Database session
            department_id: Filter by department (None for all)
            
        Returns:
            Dictionary with summary statistics
        """
        query = db.query(Application)
        if department_id:
            query = query.filter(Application.department_id == department_id)
        
        total_applications = query.count()
        ai_evaluated = query.filter(Application.ai_grade.isnot(None)).count()
        user_evaluated = query.filter(Application.user_grade.isnot(None)).count()
        
        # Calculate average AI grade
        grade_mapping = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}
        ai_grades = [app.ai_grade for app in query.filter(Application.ai_grade.isnot(None)).all()]
        avg_ai_grade = sum(grade_mapping.get(g, 0) for g in ai_grades) / len(ai_grades) if ai_grades else 0
        avg_ai_grade_letter = self._score_to_grade(avg_ai_grade)
        
        return {
            "total_applications": total_applications,
            "ai_evaluated": ai_evaluated,
            "user_evaluated": user_evaluated,
            "pending": total_applications - ai_evaluated,
            "avg_ai_grade": avg_ai_grade_letter,
            "avg_ai_score": round(avg_ai_grade, 2)
        }
    
    def get_department_stats(self, db: Session) -> List[Dict[str, Any]]:
        """
        Get statistics by department
        
        Returns:
            List of department statistics
        """
        # Query departments with application counts
        departments = db.query(
            Department.id,
            Department.name,
            Department.total_employees,
            func.count(Application.id).label('application_count')
        ).outerjoin(Application).group_by(Department.id).all()
        
        result = []
        for dept_id, dept_name, total_emp, app_count in departments:
            # Get grade distribution for department
            grades = db.query(Application.ai_grade).filter(
                Application.department_id == dept_id,
                Application.ai_grade.isnot(None)
            ).all()
            
            grade_dist = self._calculate_grade_distribution([g[0] for g in grades])
            
            # Calculate participation rate
            participation_rate = (app_count / total_emp * 100) if total_emp > 0 else 0
            
            result.append({
                "department_id": dept_id,
                "department_name": dept_name,
                "total_employees": total_emp,
                "application_count": app_count,
                "participation_rate": round(participation_rate, 2),
                "grade_distribution": grade_dist,
                "avg_grade": self._calculate_avg_grade([g[0] for g in grades])
            })
        
        return result
    
    def get_category_stats(self, db: Session, department_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get statistics by AI category
        
        Args:
            db: Database session
            department_id: Filter by department (None for all)
            
        Returns:
            List of category statistics
        """
        categories = db.query(AICategory).filter(AICategory.is_active == True).all()
        
        result = []
        for category in categories:
            query = db.query(Application).filter(
                Application.ai_category_primary == category.name
            )
            if department_id:
                query = query.filter(Application.department_id == department_id)
            
            applications = query.all()
            count = len(applications)
            
            if count > 0:
                grades = [app.ai_grade for app in applications if app.ai_grade]
                grade_dist = self._calculate_grade_distribution(grades)
                avg_grade = self._calculate_avg_grade(grades)
                
                result.append({
                    "category": category.name,
                    "count": count,
                    "grade_distribution": grade_dist,
                    "avg_grade": avg_grade
                })
        
        return sorted(result, key=lambda x: x["count"], reverse=True)
    
    def get_grade_distribution(self, db: Session, department_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get grade distribution for AI and user evaluations
        
        Args:
            db: Database session
            department_id: Filter by department (None for all)
            
        Returns:
            Dictionary with grade distributions
        """
        query = db.query(Application)
        if department_id:
            query = query.filter(Application.department_id == department_id)
        
        applications = query.all()
        
        ai_grades = [app.ai_grade for app in applications if app.ai_grade]
        user_grades = [app.user_grade for app in applications if app.user_grade]
        
        return {
            "ai_grade_distribution": self._calculate_grade_distribution(ai_grades),
            "user_grade_distribution": self._calculate_grade_distribution(user_grades),
            "ai_vs_user_comparison": self._compare_grades(applications)
        }
    
    def get_tech_skill_stats(self, db: Session, department_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get technology skill statistics
        
        Args:
            db: Database session
            department_id: Filter by department (None for all)
            
        Returns:
            Dictionary with tech skill statistics
        """
        query = db.query(Application)
        if department_id:
            query = query.filter(Application.department_id == department_id)
        
        applications = query.filter(Application.tech_capabilities.isnot(None)).all()
        
        # Count skills
        skill_counts = {}
        skill_levels = {}
        
        for app in applications:
            if not app.tech_capabilities:
                continue
            
            for tech in app.tech_capabilities:
                skill = tech.get("skill", "Unknown")
                level = tech.get("level", 0)
                
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
                if skill not in skill_levels:
                    skill_levels[skill] = []
                skill_levels[skill].append(level)
        
        # Calculate average levels
        skill_stats = []
        for skill, count in skill_counts.items():
            avg_level = sum(skill_levels[skill]) / len(skill_levels[skill]) if skill_levels[skill] else 0
            skill_stats.append({
                "skill": skill,
                "count": count,
                "avg_level": round(avg_level, 2)
            })
        
        # Sort by count
        skill_stats.sort(key=lambda x: x["count"], reverse=True)
        
        return {
            "top_skills": skill_stats[:10],
            "total_skills": len(skill_counts),
            "total_participants": len(applications)
        }
    
    def _calculate_grade_distribution(self, grades: List[str]) -> Dict[str, int]:
        """Calculate grade distribution"""
        dist = {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0}
        for grade in grades:
            if grade in dist:
                dist[grade] += 1
        return dist
    
    def _calculate_avg_grade(self, grades: List[str]) -> str:
        """Calculate average grade"""
        grade_mapping = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}
        scores = [grade_mapping.get(g, 0) for g in grades if g]
        avg_score = sum(scores) / len(scores) if scores else 0
        return self._score_to_grade(avg_score)
    
    def _score_to_grade(self, score: float) -> str:
        """Convert score to grade"""
        if score >= 4.5:
            return "S"
        elif score >= 3.5:
            return "A"
        elif score >= 2.5:
            return "B"
        elif score >= 1.5:
            return "C"
        else:
            return "D"
    
    def _compare_grades(self, applications: List[Application]) -> List[Dict[str, int]]:
        """Compare AI vs User grades"""
        comparison = []
        for app in applications:
            if app.ai_grade and app.user_grade:
                comparison.append({
                    "ai_grade": app.ai_grade,
                    "user_grade": app.user_grade
                })
        return comparison


# Singleton instance
statistics_service = StatisticsService()
