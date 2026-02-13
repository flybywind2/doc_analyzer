"""
Migration script to add user_departments association table
for many-to-many relationship between users and departments
"""
import sys
from sqlalchemy import create_engine, text, inspect
from app.config import settings
from app.database import Base
from app.models.user import User, user_departments
from app.models.department import Department


def migrate():
    """Add user_departments table to database"""
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)

    print("🔍 Checking database schema...")

    # Check if user_departments table already exists
    if 'user_departments' in inspector.get_table_names():
        print("✅ user_departments table already exists")
        return

    print("📝 Creating user_departments association table...")

    # Create the user_departments table
    user_departments.create(engine)

    print("✅ user_departments table created successfully")

    # Migrate existing single department assignments to new system
    print("\n📝 Migrating existing department assignments...")

    with engine.connect() as conn:
        # Get all users with a department_id
        result = conn.execute(text(
            "SELECT id, department_id FROM users WHERE department_id IS NOT NULL"
        ))

        users_with_dept = result.fetchall()

        if users_with_dept:
            print(f"   Found {len(users_with_dept)} users with department assignments")

            # Insert into user_departments table
            for user_id, dept_id in users_with_dept:
                # Check if already exists (in case of re-run)
                existing = conn.execute(text(
                    "SELECT 1 FROM user_departments WHERE user_id = :uid AND department_id = :did"
                ), {"uid": user_id, "did": dept_id}).fetchone()

                if not existing:
                    conn.execute(text(
                        "INSERT INTO user_departments (user_id, department_id) VALUES (:uid, :did)"
                    ), {"uid": user_id, "did": dept_id})
                    print(f"   ✓ Migrated user {user_id} -> department {dept_id}")

            conn.commit()
            print(f"✅ Migrated {len(users_with_dept)} department assignments")
        else:
            print("   No users with department assignments to migrate")

    print("\n✨ Migration completed successfully!")
    print("\n📌 Note: Existing department_id field in users table is preserved for backward compatibility")
    print("   Users can now be assigned to multiple departments via the user_departments table")


if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}", file=sys.stderr)
        sys.exit(1)
