import os
import json
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, Response, current_app, send_from_directory
from werkzeug.utils import secure_filename
from app import db
from app.models import Batch, Check
from app.processor import CheckProcessor, get_processing_status
from app.hubspot import HubSpotClient
from config import Config

main_bp = Blueprint('main', __name__)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS

@main_bp.route('/')
def index():
    batches = Batch.query.order_by(Batch.upload_date.desc()).limit(10).all()
    return render_template('index.html', 
                         batches=batches,
                         appeal_codes=Config.APPEAL_CODES)

@main_bp.route('/upload', methods=['POST'])
def upload():
    if 'pdf_file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['pdf_file']
    appeal_code = request.form.get('appeal_code', '020')
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not file.filename or not allowed_file(file.filename):
        return jsonify({'error': 'Only PDF files are allowed'}), 400
    
    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_filename = f"{timestamp}_{filename}"
    
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
    file.save(filepath)
    
    batch = Batch()
    batch.filename = filename
    batch.appeal_code = appeal_code
    batch.status = 'processing'
    db.session.add(batch)
    db.session.commit()
    
    from flask import current_app as app
    processor = CheckProcessor(app)
    processor.process_batch(batch.id, filepath, appeal_code)
    
    return jsonify({
        'success': True,
        'batch_id': batch.id,
        'redirect': f'/processing/{batch.id}'
    })

@main_bp.route('/processing/<int:batch_id>')
def processing(batch_id):
    batch = db.session.get(Batch, batch_id)
    if not batch:
        return "Batch not found", 404
    return render_template('processing.html', batch=batch)

@main_bp.route('/api/status/<int:batch_id>')
def get_status(batch_id):
    def generate():
        import time
        while True:
            status = get_processing_status(batch_id)
            yield f"data: {json.dumps(status)}\n\n"
            
            if status.get('status') in ['complete', 'error']:
                break
            
            time.sleep(1)
    
    return Response(generate(), mimetype='text/event-stream')

@main_bp.route('/review/<int:batch_id>')
def review(batch_id):
    batch = db.session.get(Batch, batch_id)
    if not batch:
        return "Batch not found", 404
    
    checks = Check.query.filter_by(batch_id=batch_id).order_by(Check.page_number).all()
    
    total_amount = sum(float(c.amount or 0) for c in checks)
    
    hubspot_configured = HubSpotClient().is_configured()
    
    return render_template('review.html', 
                         batch=batch, 
                         checks=checks,
                         total_amount=total_amount,
                         hubspot_configured=hubspot_configured,
                         is_bank_batch=(batch.appeal_code == '035'))

@main_bp.route('/api/check/<int:check_id>', methods=['GET', 'PUT'])
def check_api(check_id):
    check = db.session.get(Check, check_id)
    if not check:
        return jsonify({'error': 'Check not found'}), 404
    
    if request.method == 'GET':
        return jsonify(check.to_dict())
    
    data = request.get_json()
    
    if 'amount' in data:
        try:
            check.amount = float(data['amount']) if data['amount'] else None
        except ValueError:
            pass
    
    if 'check_date' in data:
        try:
            check.check_date = datetime.strptime(data['check_date'], '%Y-%m-%d').date() if data['check_date'] else None
        except ValueError:
            pass
    
    for field in ['check_number', 'name', 'address_line1', 'address_line2', 
                  'city', 'state', 'zip_code', 'hubspot_contact_id']:
        if field in data:
            setattr(check, field, data[field])
    
    if 'needs_review' in data:
        check.needs_review = data['needs_review']
    
    db.session.commit()
    return jsonify(check.to_dict())

@main_bp.route('/api/search_contacts')
def search_contacts():
    name = request.args.get('name', '')
    zip_code = request.args.get('zip', '')
    
    hubspot = HubSpotClient()
    if not hubspot.is_configured():
        return jsonify({'error': 'HubSpot not configured'}), 400
    
    contacts = hubspot.search_contacts(name, zip_code)
    return jsonify({'contacts': contacts})

@main_bp.route('/api/submit/<int:batch_id>', methods=['POST'])
def submit_batch(batch_id):
    batch = db.session.get(Batch, batch_id)
    if not batch:
        return jsonify({'error': 'Batch not found'}), 404
    
    hubspot = HubSpotClient()
    if not hubspot.is_configured():
        return jsonify({'error': 'HubSpot not configured'}), 400
    
    checks = Check.query.filter_by(batch_id=batch_id).all()
    
    success_count = 0
    errors = []
    
    for check in checks:
        if check.is_money_order:
            continue
        
        if not check.amount:
            errors.append(f"Check #{check.page_number}: Missing amount")
            continue
        
        deal_id = hubspot.create_deal(
            check.to_dict(),
            check.hubspot_contact_id,
            batch.appeal_code
        )
        
        if deal_id:
            check.hubspot_deal_id = deal_id
            success_count += 1
        else:
            errors.append(f"Check #{check.page_number}: Failed to create deal")
    
    batch.status = 'submitted'
    batch.submitted_date = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'success': True,
        'deals_created': success_count,
        'errors': errors
    })

@main_bp.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@main_bp.route('/api/batches')
def list_batches():
    batches = Batch.query.order_by(Batch.upload_date.desc()).all()
    return jsonify([b.to_dict() for b in batches])

@main_bp.route('/api/batch/<int:batch_id>', methods=['DELETE'])
def delete_batch(batch_id):
    batch = db.session.get(Batch, batch_id)
    if not batch:
        return jsonify({'error': 'Batch not found'}), 404
    
    db.session.delete(batch)
    db.session.commit()
    
    return jsonify({'success': True})
