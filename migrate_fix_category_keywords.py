"""
Migration script to fix category keywords column
Convert Text type to JSON type and parse existing string data
"""
import sys
import json
from sqlalchemy import create_engine, text, inspect
from app.config import settings


def migrate():
    """Fix category keywords column type"""
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)

    print("🔍 Checking ai_categories table...")

    # Check if table exists
    if 'ai_categories' not in inspector.get_table_names():
        print("⚠️  ai_categories table does not exist")
        return

    with engine.connect() as conn:
        # Get current keywords data
        print("📝 Reading existing keywords data...")
        result = conn.execute(text("SELECT id, keywords FROM ai_categories"))
        categories = result.fetchall()

        # Store parsed keywords
        keywords_data = {}
        for cat_id, keywords_str in categories:
            if keywords_str:
                try:
                    # Try to parse as JSON
                    parsed = json.loads(keywords_str)
                    if isinstance(parsed, list):
                        keywords_data[cat_id] = parsed
                    else:
                        keywords_data[cat_id] = None
                    print(f"  ✓ Category {cat_id}: parsed JSON successfully")
                except json.JSONDecodeError:
                    # If not JSON, treat as comma-separated string
                    if ',' in keywords_str:
                        keywords_data[cat_id] = [k.strip() for k in keywords_str.split(',') if k.strip()]
                        print(f"  ✓ Category {cat_id}: converted comma-separated string")
                    else:
                        keywords_data[cat_id] = [keywords_str.strip()] if keywords_str.strip() else None
                        print(f"  ✓ Category {cat_id}: converted single string")
            else:
                keywords_data[cat_id] = None

        # For SQLite, we need to recreate the table
        print("\n📝 Recreating table with JSON column...")

        # Create backup table
        conn.execute(text("""
            CREATE TABLE ai_categories_backup AS
            SELECT * FROM ai_categories
        """))
        conn.commit()
        print("  ✓ Created backup table")

        # Drop original table
        conn.execute(text("DROP TABLE ai_categories"))
        conn.commit()
        print("  ✓ Dropped original table")

        # Recreate table with JSON column
        conn.execute(text("""
            CREATE TABLE ai_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(50) UNIQUE NOT NULL,
                description TEXT,
                keywords JSON,
                display_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            )
        """))
        conn.commit()
        print("  ✓ Recreated table with JSON column")

        # Restore data with converted keywords
        backup_result = conn.execute(text("SELECT * FROM ai_categories_backup"))
        for row in backup_result:
            cat_id = row[0]
            keywords_json = json.dumps(keywords_data.get(cat_id)) if keywords_data.get(cat_id) else None

            conn.execute(text("""
                INSERT INTO ai_categories
                (id, name, description, keywords, display_order, is_active, created_at, updated_at)
                VALUES (:id, :name, :description, :keywords, :display_order, :is_active, :created_at, :updated_at)
            """), {
                "id": row[0],
                "name": row[1],
                "description": row[2],
                "keywords": keywords_json,
                "display_order": row[4],
                "is_active": row[5],
                "created_at": row[6],
                "updated_at": row[7]
            })

        conn.commit()
        print("  ✓ Restored data with converted keywords")

        # Drop backup table
        conn.execute(text("DROP TABLE ai_categories_backup"))
        conn.commit()
        print("  ✓ Dropped backup table")

    print("\n✨ Migration completed successfully!")
    print("   Category keywords are now stored as JSON arrays")


if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        print(f"\n❌ Migration failed: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
