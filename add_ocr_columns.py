#!/usr/bin/env python3
"""
Database migration: Add check_ocr_text and buckslip_ocr_text columns
"""
from app import create_app, db

def migrate():
    app = create_app()
    with app.app_context():
        # Add new columns using raw SQL
        with db.engine.connect() as conn:
            try:
                # Add check_ocr_text column
                conn.execute(db.text(
                    "ALTER TABLE checks ADD COLUMN check_ocr_text TEXT"
                ))
                print("✓ Added check_ocr_text column")
            except Exception as e:
                print(f"check_ocr_text column might already exist: {e}")

            try:
                # Add buckslip_ocr_text column
                conn.execute(db.text(
                    "ALTER TABLE checks ADD COLUMN buckslip_ocr_text TEXT"
                ))
                print("✓ Added buckslip_ocr_text column")
            except Exception as e:
                print(f"buckslip_ocr_text column might already exist: {e}")

            conn.commit()

        print("\n✓ Migration complete!")
        print("\nThese new columns will store separate OCR text for:")
        print("  - check_ocr_text: Raw OCR from check image")
        print("  - buckslip_ocr_text: Raw OCR from buckslip image")
        print("\nThis enables the new click-to-fill feature in the review page.")

if __name__ == '__main__':
    migrate()
