"""
CampusWatt Database Seeding Script
Populates SQLite / relational database with labelled demonstration data.
"""
import sys
from backend.database import Base, engine, SessionLocal
from backend.seed_data import seed_database


def main():
    print("Initializing CampusWatt database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        print("Seeding sample campus, buildings, 90 days of energy readings, and alerts...")
        res = seed_database(db, clear_existing=True)
        print(f"Success! Seeded {res['buildings']} buildings, {res['readings']} hourly energy readings, and initial alerts.")
        print("All records are clearly labelled as sample demonstration data.")
    except Exception as e:
        print(f"Error seeding database: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
