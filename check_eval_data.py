"""
Check AI Evaluation Detail JSON Structure
"""
from app.database import SessionLocal
from app.models.application import Application
import json

db = SessionLocal()
app = db.query(Application).filter(Application.ai_evaluation_detail != None).first()

if app:
    print("="*80)
    print(f"Application ID: {app.id}")
    print(f"Application Subject: {app.subject}")
    print("="*80)
    print("\nai_evaluation_detail JSON:")
    print("="*80)
    print(json.dumps(app.ai_evaluation_detail, indent=2, ensure_ascii=False))
    print("="*80)
else:
    print("No evaluated applications found")

db.close()
