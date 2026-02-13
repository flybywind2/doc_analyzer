"""
Check most recent AI evaluation data structure
최신 AI 평가 데이터 구조 확인
"""
from app.database import SessionLocal
from app.models.application import Application
from sqlalchemy import desc
import json

db = SessionLocal()

# Get most recently evaluated application
app = db.query(Application).filter(
    Application.ai_evaluation_detail != None
).order_by(desc(Application.ai_evaluated_at)).first()

if app:
    print("="*80)
    print(f"Application ID: {app.id}")
    print(f"Subject: {app.subject}")
    print(f"AI Evaluated At: {app.ai_evaluated_at}")
    print("="*80)

    eval_detail = app.ai_evaluation_detail

    # Check if evaluation_scores exists (new format)
    if isinstance(eval_detail, dict) and "evaluation_scores" in eval_detail:
        print("\n[OK] NEW FORMAT DETECTED (evaluation_scores exists)")
        print("="*80)

        eval_scores = eval_detail["evaluation_scores"]
        print(f"\nNumber of criteria: {len(eval_scores)}")

        # Check first criterion
        if eval_scores:
            first_criterion = list(eval_scores.keys())[0]
            first_data = eval_scores[first_criterion]

            print(f"\nFirst criterion: {first_criterion}")
            print(json.dumps(first_data, indent=2, ensure_ascii=False))

            # Check for 3-step debate structure
            if "score_a_initial" in first_data and "score_b_review" in first_data and "score_a_final" in first_data:
                print("\n[SUCCESS] 3-STEP DEBATE STRUCTURE CONFIRMED!")
                print(f"  - score_a_initial: {first_data['score_a_initial']}")
                print(f"  - score_b_review: {first_data['score_b_review']}")
                print(f"  - score_a_final: {first_data['score_a_final']}")
            else:
                print("\n[WARNING] OLD STRUCTURE (missing score_a_initial/score_b_review/score_a_final)")

    else:
        print("\n[WARNING] OLD FORMAT DETECTED (no evaluation_scores)")
        print("="*80)
        print("\nDirect structure:")
        print(json.dumps(eval_detail, indent=2, ensure_ascii=False))
else:
    print("No evaluated applications found")

db.close()
