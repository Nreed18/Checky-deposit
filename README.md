# Check Processor

An automated check processing system that uses AI OCR to extract check data from remote deposit PDFs and creates donation deals in HubSpot CRM.

## Overview

This application converts physical checks (from remote deposit PDFs) into HubSpot CRM deals using OCR technology. It automates the tedious process of manually entering check data, saving 50+ minutes per batch while maintaining accuracy through human review.

## Features

- **PDF Upload**: Upload remote deposit PDFs with appeal code selection (035 Bank Check / 020 General Mail)
- **Intelligent Image Pairing**: For bank batches (035), pairs buck slips with check images
- **Smart Data Extraction**: Uses buck slip for donor info in bank batches, check for general mail
- **AI OCR**: Extracts amount, date, check number, name, address from images using OnnxTR and Tesseract
- **HubSpot Matching**: Fuzzy search for existing contacts with confidence scoring
- **Review Interface**: Color-coded rows, inline editing, dual image display
- **HubSpot Deal Creation**: Creates deals with proper associations

## Tech Stack

- **Backend**: Python 3.11+ with Flask
- **Database**: PostgreSQL
- **OCR Engine**: OnnxTR (docTR CPU) with Tesseract fallback
- **CRM Integration**: HubSpot API
- **Frontend**: HTML/CSS/JavaScript with Server-Sent Events

## Prerequisites

Before installing, ensure you have the following installed on your system:

- **Python 3.11 or higher**
- **PostgreSQL** (version 12 or higher recommended)
- **Tesseract OCR** (system package)
- **Poppler utilities** (for PDF processing)

### System Dependencies Installation

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr poppler-utils postgresql postgresql-contrib
```

#### macOS
```bash
brew install tesseract poppler postgresql
brew services start postgresql
```

#### Fedora/RHEL/CentOS
```bash
sudo dnf install -y tesseract poppler-utils postgresql postgresql-server
sudo postgresql-setup --initdb
sudo systemctl start postgresql
```

#### Windows
1. Download and install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
2. Download and install [Poppler for Windows](http://blog.alivate.com.au/poppler-windows/)
3. Install [PostgreSQL](https://www.postgresql.org/download/windows/)
4. Add Tesseract and Poppler to your system PATH

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/Checky-deposit.git
cd Checky-deposit
```

### 2. Set Up Python Environment

This project uses `uv` for fast dependency management. If you don't have `uv` installed:

```bash
# Install uv (recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or use pip
pip install uv
```

Install dependencies:

```bash
# Using uv (recommended - much faster)
uv sync

# Or using pip
pip install -r requirements.txt  # You may need to generate this from pyproject.toml
```

### 3. Set Up PostgreSQL Database

Create a new PostgreSQL database:

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database and user
CREATE DATABASE check_processor;
CREATE USER check_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE check_processor TO check_user;
\q
```

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# Database Configuration
DATABASE_URL=postgresql://check_user:your_secure_password@localhost:5432/check_processor

# Flask Session Secret (generate a random string)
SESSION_SECRET=your-random-secret-key-change-this

# HubSpot API Key (optional - required for CRM integration)
HUBSPOT_API_KEY=your-hubspot-api-key
```

To generate a secure session secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Initialize the Database

The database tables will be created automatically when you first run the application.

### 6. Create Uploads Directory

```bash
mkdir -p uploads
```

## Running the Application

### Development Mode

```bash
python run.py
```

The application will start on `http://localhost:5000`

### Production Mode (using Gunicorn)

```bash
gunicorn -w 4 -b 0.0.0.0:5000 --timeout 300 run:app
```

Options:
- `-w 4`: Run with 4 worker processes (adjust based on CPU cores)
- `--timeout 300`: Set timeout to 5 minutes (OCR processing can take time)

## Usage

1. **Upload PDF**: Navigate to `http://localhost:5000` and upload a remote deposit PDF
2. **Select Appeal Code**:
   - `035` for Bank Check batches (includes buck slips)
   - `020` for General Mail batches (checks only)
3. **Enter Expected Total**: (Optional) Enter the expected batch total for validation
4. **Processing**: Watch real-time progress as the system extracts and processes checks
5. **Review**: Review extracted data, edit as needed, and verify HubSpot contact matches
6. **Submit**: Submit to create deals in HubSpot

## Configuration

### Data Retention

By default, uploaded files and database records are retained for 48 hours. Modify in `config.py`:

```python
DATA_RETENTION_HOURS = 48  # Change as needed
```

### File Upload Limits

Maximum file size is set to 100MB. Modify in `config.py`:

```python
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # Adjust as needed
```

### Appeal Codes

Customize appeal codes in `config.py`:

```python
APPEAL_CODES = {
    '035': 'Bank Check',
    '020': 'General Mail',
    # Add more codes as needed
}
```

## Troubleshooting

### Tesseract Not Found
If you see "tesseract not found" errors:
- Verify installation: `tesseract --version`
- Ubuntu/Debian: Ensure `/usr/bin/tesseract` exists
- Windows: Add Tesseract installation directory to PATH

### PDF Processing Errors
If PDF processing fails:
- Verify Poppler installation: `pdftoppm -v`
- Ensure PDFs are not password-protected
- Check file permissions in the `uploads/` directory

### Database Connection Errors
- Verify PostgreSQL is running: `sudo systemctl status postgresql`
- Check DATABASE_URL format in `.env`
- Ensure database user has proper permissions

### Port Already in Use
If port 5000 is already in use:
```bash
# Find process using port 5000
lsof -i :5000

# Kill the process or use a different port
python run.py --port 8000
```

## Project Structure

```
/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── routes.py            # Web routes (upload, review, submit)
│   ├── processor.py         # Background OCR processing
│   ├── ocr.py               # OCR engine wrapper
│   ├── hubspot.py           # HubSpot API integration
│   ├── models.py            # Database models
│   ├── templates/           # HTML templates
│   └── static/              # CSS/JS assets
├── config.py                # Application configuration
├── run.py                   # Application entry point
├── pyproject.toml           # Python dependencies
└── uploads/                 # Uploaded files (gitignored)
```

## Development

### Running Tests
```bash
# Add test commands when tests are implemented
python -m pytest
```

### Code Style
This project follows PEP 8 style guidelines.

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

## Support

For issues and questions, please [open an issue](https://github.com/yourusername/Checky-deposit/issues) on GitHub.
