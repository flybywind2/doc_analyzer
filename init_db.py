#!/usr/bin/env python3
"""
Database Initialization Script
PC 환경에서 clone 후 최초 실행 시 사용하는 스크립트입니다.
"""
import os
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Initialize database with default data"""
    print("=" * 60)
    print("AI Application Evaluator - Database Initialization")
    print("=" * 60)
    
    # Check if data directory exists
    data_dir = Path("data")
    if not data_dir.exists():
        print(f"📁 Creating data directory: {data_dir}")
        data_dir.mkdir(parents=True, exist_ok=True)
    
    # Import after ensuring path is set
    from app.database import init_db, SessionLocal
    from app.models.init_data import init_default_data
    from app.models.generate_dummy_data import generate_dummy_data
    
    # Initialize database schema
    print("\n🔨 Creating database tables...")
    init_db()
    print("✅ Database schema created successfully")
    
    # Initialize default data
    print("\n📊 Initializing default data...")
    db = SessionLocal()
    try:
        init_default_data(db)
        print("✅ Default data initialized")
        
        # Ask user if they want to generate dummy data
        response = input("\n❓ Generate dummy test data? (y/n) [default: n]: ").strip().lower()
        if response == 'y':
            print("\n🎲 Generating dummy data for testing...")
            generate_dummy_data(db)
            print("✅ Dummy data generated successfully")
        else:
            print("⏭️  Skipping dummy data generation")
            
    except Exception as e:
        print(f"❌ Error during initialization: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()
    
    # Check database file
    db_file = Path("data/app.db")
    if db_file.exists():
        size_kb = db_file.stat().st_size / 1024
        print(f"\n✅ Database file created: {db_file} ({size_kb:.2f} KB)")
    
    print("\n" + "=" * 60)
    print("🎉 Database initialization completed!")
    print("=" * 60)
    print("\n📝 Next steps:")
    print("   1. Configure .env file with your settings")
    print("   2. Run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
    print("   3. Access: http://localhost:8000")
    print("\n👤 Default admin account:")
    print("   Username: admin")
    print("   Password: admin123!")
    print("=" * 60)

if __name__ == "__main__":
    main()
