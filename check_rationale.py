"""
Check rationale field in evaluation_scores
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
    print(f"AI Evaluated At: {app.ai_evaluated_at}")
    print("="*80)

    eval_detail = app.ai_evaluation_detail

    if isinstance(eval_detail, dict) and "evaluation_scores" in eval_detail:
        eval_scores = eval_detail["evaluation_scores"]

        # Check first criterion
        if eval_scores:
            first_criterion = list(eval_scores.keys())[0]
            first_data = eval_scores[first_criterion]

            print(f"\nFirst criterion: {first_criterion}")
            print(f"\nFull data structure:")
            print(json.dumps(first_data, indent=2, ensure_ascii=False))

            print(f"\n{'='*80}")
            print("Rationale content:")
            print(f"{'='*80}")
            rationale = first_data.get("rationale", "")
            print(rationale)

            # Check if it contains all 3 steps
            has_step1 = "Step 1" in rationale or "LLM A 초기" in rationale
            has_step2 = "Step 2" in rationale or "LLM B 검토" in rationale
            has_step3 = "Step 3" in rationale or "LLM A 최종" in rationale

            print(f"\n{'='*80}")
            print("Step detection:")
            print(f"{'='*80}")
            print(f"Has Step 1: {has_step1}")
            print(f"Has Step 2: {has_step2}")
            print(f"Has Step 3: {has_step3}")

            # Check score fields
            print(f"\n{'='*80}")
            print("Score fields:")
            print(f"{'='*80}")
            print(f"score: {first_data.get('score')}")
            print(f"score_a_initial: {first_data.get('score_a_initial')}")
            print(f"score_b_review: {first_data.get('score_b_review')}")
            print(f"score_a_final: {first_data.get('score_a_final')}")

    else:
        print("\n[WARNING] Old format - no evaluation_scores")
        print(json.dumps(eval_detail, indent=2, ensure_ascii=False))
else:
    print("No evaluated applications found")

db.close()
