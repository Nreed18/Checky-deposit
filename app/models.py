from datetime import datetime
from app import db

class Batch(db.Model):
    __tablename__ = 'batches'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    appeal_code = db.Column(db.String(10), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='processing')
    total_checks = db.Column(db.Integer, default=0)
    expected_amount = db.Column(db.Numeric(12, 2), nullable=True)
    submitted_date = db.Column(db.DateTime, nullable=True)
    
    checks = db.relationship('Check', backref='batch', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'appeal_code': self.appeal_code,
            'upload_date': self.upload_date.isoformat() if self.upload_date else None,
            'status': self.status,
            'total_checks': self.total_checks,
            'expected_amount': float(self.expected_amount) if self.expected_amount else None,
            'submitted_date': self.submitted_date.isoformat() if self.submitted_date else None
        }

class Check(db.Model):
    __tablename__ = 'checks'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'), nullable=False)
    page_number = db.Column(db.Integer, nullable=False)
    
    amount = db.Column(db.Numeric(10, 2), nullable=True)
    check_date = db.Column(db.Date, nullable=True)
    check_number = db.Column(db.String(50), nullable=True)
    
    name = db.Column(db.String(255), nullable=True)
    address_line1 = db.Column(db.String(255), nullable=True)
    address_line2 = db.Column(db.String(255), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(2), nullable=True)
    zip_code = db.Column(db.String(10), nullable=True)
    
    hubspot_contact_id = db.Column(db.String(50), nullable=True)
    hubspot_contact_name = db.Column(db.String(255), nullable=True)
    match_confidence = db.Column(db.Float, default=0.0)
    
    is_money_order = db.Column(db.Boolean, default=False)
    needs_review = db.Column(db.Boolean, default=True)

    hubspot_deal_id = db.Column(db.String(50), nullable=True)

    raw_ocr_text = db.Column(db.Text, nullable=True)
    check_ocr_text = db.Column(db.Text, nullable=True)  # Separate check OCR
    buckslip_ocr_text = db.Column(db.Text, nullable=True)  # Separate buckslip OCR

    check_image_path = db.Column(db.String(500), nullable=True)
    buckslip_image_path = db.Column(db.String(500), nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'page_number': self.page_number,
            'amount': float(self.amount) if self.amount else None,
            'check_date': self.check_date.isoformat() if self.check_date else None,
            'check_number': self.check_number,
            'name': self.name,
            'address_line1': self.address_line1,
            'address_line2': self.address_line2,
            'city': self.city,
            'state': self.state,
            'zip_code': self.zip_code,
            'hubspot_contact_id': self.hubspot_contact_id,
            'hubspot_contact_name': self.hubspot_contact_name,
            'match_confidence': self.match_confidence,
            'is_money_order': self.is_money_order,
            'needs_review': self.needs_review,
            'hubspot_deal_id': self.hubspot_deal_id,
            'check_image_path': self.check_image_path,
            'buckslip_image_path': self.buckslip_image_path
        }
