-- Migration: Add check_ocr_text and buckslip_ocr_text columns
-- Run this with: psql -d your_database_name -f migrate_add_ocr_columns.sql

-- Add check_ocr_text column
ALTER TABLE checks ADD COLUMN IF NOT EXISTS check_ocr_text TEXT;

-- Add buckslip_ocr_text column
ALTER TABLE checks ADD COLUMN IF NOT EXISTS buckslip_ocr_text TEXT;

-- Display success message
SELECT 'Migration complete! Added check_ocr_text and buckslip_ocr_text columns.' AS status;
