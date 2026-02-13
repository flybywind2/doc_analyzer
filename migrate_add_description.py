#!/usr/bin/env python3
"""
Add description column to departments table
"""
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import engine
from sqlalchemy import text


def migrate():
    """Add description column to departments table"""
    print("=" * 60)
    print("Database Migration: Add description to departments")
    print("=" * 60)

    try:
        with engine.connect() as conn:
            # Check if column already exists
            result = conn.execute(text("PRAGMA table_info(departments)")).fetchall()
            columns = [row[1] for row in result]

            if 'description' in columns:
                print("[OK] Column 'description' already exists. No migration needed.")
                return

            print("\n[*] Adding 'description' column to departments table...")

            # Add description column
            conn.execute(text("ALTER TABLE departments ADD COLUMN description VARCHAR(500)"))
            conn.commit()

            print("[OK] Column added successfully!")

            # Verify
            result = conn.execute(text("PRAGMA table_info(departments)")).fetchall()
            print(f"\n[OK] Current departments table schema:")
            for row in result:
                print(f"   - {row[1]} ({row[2]})")

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("[SUCCESS] Migration completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    migrate()
