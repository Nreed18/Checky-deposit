import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

def create_app():
    app = Flask(__name__)
    
    from config import Config
    app.config.from_object(Config)
    
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
    
    @app.after_request
    def add_header(response):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    db.init_app(app)

    with app.app_context():
        from app import models
        db.create_all()

        # Auto-migrate: Add new columns if they don't exist
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                # Add check_ocr_text column
                try:
                    conn.execute(text("ALTER TABLE checks ADD COLUMN IF NOT EXISTS check_ocr_text TEXT"))
                    conn.commit()
                except Exception:
                    pass  # Column already exists

                # Add buckslip_ocr_text column
                try:
                    conn.execute(text("ALTER TABLE checks ADD COLUMN IF NOT EXISTS buckslip_ocr_text TEXT"))
                    conn.commit()
                except Exception:
                    pass  # Column already exists
        except Exception as e:
            print(f"Note: Database migration check: {e}")

    from app.routes import main_bp
    app.register_blueprint(main_bp)
    
    return app
