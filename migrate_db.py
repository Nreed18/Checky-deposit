#!/usr/bin/env python3
"""Quick database migration using SQLAlchemy text"""
import os
import sys

# Set Flask config before importing app
os.environ.setdefault('FLASK_APP', 'run.py')

try:
    from app import create_app, db
    from sqlalchemy import text

    app = create_app()

    with app.app_context():
        print("Running database migration...")

        try:
            # Add check_ocr_text column
            db.session.execute(text("ALTER TABLE checks ADD COLUMN IF NOT EXISTS check_ocr_text TEXT"))
            print("✓ Added check_ocr_text column")
        except Exception as e:
            print(f"Note: check_ocr_text - {e}")

        try:
            # Add buckslip_ocr_text column
            db.session.execute(text("ALTER TABLE checks ADD COLUMN IF NOT EXISTS buckslip_ocr_text TEXT"))
            print("✓ Added buckslip_ocr_text column")
        except Exception as e:
            print(f"Note: buckslip_ocr_text - {e}")

        db.session.commit()
        print("\n✓ Migration complete!")

except ImportError as e:
    print(f"Error: {e}")
    print("\nCouldn't import Flask. Please ensure you're in the correct environment.")
    print("Activate your virtual environment first:")
    print("  source venv/bin/activate  # or your virtualenv")
    sys.exit(1)
