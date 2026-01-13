# Check Processor

An automated check processing system that uses AI OCR to extract check data from remote deposit PDFs and creates donation deals in HubSpot CRM.

## Overview

This application converts physical checks (from remote deposit PDFs) into HubSpot CRM deals using OCR technology. It automates the tedious process of manually entering check data, saving 50+ minutes per batch while maintaining accuracy through human review.

## Architecture

- **Backend**: Python 3.11 + Flask web framework
- **Database**: PostgreSQL (stores batches, checks, processing state)
- **OCR Engine**: Tesseract OCR (runs locally, no cloud APIs)
- **CRM Integration**: HubSpot API
- **Frontend**: HTML/CSS/JavaScript with Server-Sent Events (live updates)

## Project Structure

```
/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── routes.py             # Web routes (upload, review, submit)
│   ├── processor.py          # Background OCR processing
│   ├── ocr.py                # Tesseract OCR engine wrapper
│   ├── hubspot.py            # HubSpot API integration
│   ├── models.py             # Database models (Batch, Check)
│   ├── templates/            # HTML templates
│   │   ├── index.html        # Upload page
│   │   ├── processing.html   # Live progress page
│   │   └── review.html       # Check review/edit page
│   └── static/               # CSS/JS
├── config.py                 # Configuration
├── run.py                    # Application entry point
└── uploads/                  # Uploaded PDFs and extracted images
```

## Key Features

1. **PDF Upload**: Upload remote deposit PDFs with appeal code selection (035 Bank Check / 020 General Mail)
2. **Intelligent Image Pairing**: For bank batches (035), pairs buck slips with check images
3. **Smart Data Extraction**: Uses buck slip for donor info in bank batches, check for general mail
4. **AI OCR**: Extracts amount, date, check number, name, address from images
5. **HubSpot Matching**: Fuzzy search for existing contacts with confidence scoring
6. **Review Interface**: Color-coded rows, inline editing, dual image display
7. **HubSpot Deal Creation**: Creates deals with proper associations

## Batch Types

- **035 - Bank Check**: Includes buck slips with donor info. System pairs buck slip (donor info) with check image.
- **020 - General Mail**: Check images only. System extracts donor info from check.

## Environment Variables

- `DATABASE_URL`: PostgreSQL connection string (auto-configured)
- `SESSION_SECRET`: Flask session secret key
- `HUBSPOT_API_KEY`: HubSpot private app API key (optional, for CRM integration)

## Running the Application

The application runs on port 5000. Access the web interface to upload PDFs and process checks.

## Recent Changes

- Initial build (January 2026)
- Implemented dual image display for bank batches
- Added buck slip/check pairing logic with two-pass processing (classify pages first, then pair checks with following buckslips)
- Integrated OnnxTR (docTR CPU) as primary OCR engine with Tesseract fallback for improved accuracy
- Added expected batch total feature for validation during review
- Review page now shows "Reviewed Total vs Expected" with live updates and mismatch warnings
- Submit confirmation dialog when totals don't match
