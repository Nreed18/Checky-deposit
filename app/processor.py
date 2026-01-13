import os
import threading
from pdf2image import convert_from_path
from PIL import Image
from app import db
from app.models import Batch, Check
from app.ocr import OCREngine
from app.hubspot import HubSpotClient

processing_status = {}

class CheckProcessor:
    def __init__(self, app):
        self.app = app
        self.ocr = OCREngine()
        self.hubspot = HubSpotClient()
    
    def process_batch(self, batch_id, pdf_path, appeal_code):
        thread = threading.Thread(
            target=self._process_in_background,
            args=(batch_id, pdf_path, appeal_code)
        )
        thread.daemon = True
        thread.start()
    
    def _process_in_background(self, batch_id, pdf_path, appeal_code):
        with self.app.app_context():
            try:
                processing_status[batch_id] = {
                    'status': 'converting',
                    'current_page': 0,
                    'total_pages': 0,
                    'checks_found': 0,
                    'message': 'Converting PDF to images...'
                }
                
                images = convert_from_path(pdf_path, dpi=300)
                total_pages = len(images)
                
                processing_status[batch_id]['total_pages'] = total_pages
                processing_status[batch_id]['status'] = 'processing'
                
                batch = db.session.get(Batch, batch_id)
                if not batch:
                    processing_status[batch_id] = {'status': 'error', 'message': 'Batch not found'}
                    return
                
                image_dir = os.path.join(self.app.config['UPLOAD_FOLDER'], f'batch_{batch_id}')
                os.makedirs(image_dir, exist_ok=True)
                
                is_bank_batch = (appeal_code == '035')
                
                if is_bank_batch:
                    self._process_bank_batch(batch_id, images, image_dir)
                else:
                    self._process_mail_batch(batch_id, images, image_dir)
                
                self._match_hubspot_contacts(batch_id)
                
                batch = db.session.get(Batch, batch_id)
                if batch:
                    batch.status = 'ready'
                    batch.total_checks = Check.query.filter_by(batch_id=batch_id).count()
                    db.session.commit()
                    
                    processing_status[batch_id] = {
                        'status': 'complete',
                        'total_pages': total_pages,
                        'checks_found': batch.total_checks,
                        'message': 'Processing complete!'
                    }
                else:
                    processing_status[batch_id] = {
                        'status': 'error',
                        'total_pages': total_pages,
                        'checks_found': 0,
                        'message': 'Batch not found after processing'
                    }
                
            except Exception as e:
                print(f"Processing error: {e}")
                processing_status[batch_id] = {
                    'status': 'error',
                    'message': str(e)
                }
                
                batch = db.session.get(Batch, batch_id)
                if batch:
                    batch.status = 'error'
                    db.session.commit()
    
    def _process_bank_batch(self, batch_id, images, image_dir):
        page_num = 0
        check_count = 0
        
        while page_num < len(images):
            processing_status[batch_id]['current_page'] = page_num + 1
            processing_status[batch_id]['message'] = f'Processing page {page_num + 1} of {len(images)}...'
            
            buckslip_path = os.path.join(image_dir, f'page_{page_num + 1}_buckslip.png')
            images[page_num].save(buckslip_path, 'PNG')
            buckslip_text = self.ocr.extract_text(buckslip_path)
            
            check_path = None
            check_text = ""
            
            if page_num + 1 < len(images):
                check_path = os.path.join(image_dir, f'page_{page_num + 2}_check.png')
                images[page_num + 1].save(check_path, 'PNG')
                check_text = self.ocr.extract_text(check_path)
            
            buckslip_data = self.ocr.parse_check_data(buckslip_text, is_buckslip=True)
            check_data = self.ocr.parse_check_data(check_text, is_buckslip=False)
            
            check = Check()
            check.batch_id = batch_id
            check.page_number = page_num + 1
            check.amount = check_data.get('amount') or buckslip_data.get('amount')
            check.check_date = check_data.get('check_date') or buckslip_data.get('check_date')
            check.check_number = check_data.get('check_number') or buckslip_data.get('check_number')
            check.name = buckslip_data.get('name')
            check.address_line1 = buckslip_data.get('address_line1')
            check.address_line2 = buckslip_data.get('address_line2')
            check.city = buckslip_data.get('city')
            check.state = buckslip_data.get('state')
            check.zip_code = buckslip_data.get('zip_code')
            check.is_money_order = check_data.get('is_money_order', False)
            check.needs_review = True
            check.raw_ocr_text = f"BUCKSLIP:\n{buckslip_text}\n\nCHECK:\n{check_text}"
            check.buckslip_image_path = buckslip_path
            check.check_image_path = check_path
            
            db.session.add(check)
            db.session.commit()
            
            check_count += 1
            processing_status[batch_id]['checks_found'] = check_count
            
            page_num += 2
    
    def _process_mail_batch(self, batch_id, images, image_dir):
        check_count = 0
        
        for page_num, image in enumerate(images):
            processing_status[batch_id]['current_page'] = page_num + 1
            processing_status[batch_id]['message'] = f'Processing page {page_num + 1} of {len(images)}...'
            
            check_path = os.path.join(image_dir, f'page_{page_num + 1}_check.png')
            image.save(check_path, 'PNG')
            
            raw_text = self.ocr.extract_text(check_path)
            check_data = self.ocr.parse_check_data(raw_text, is_buckslip=False)
            
            check = Check()
            check.batch_id = batch_id
            check.page_number = page_num + 1
            check.amount = check_data.get('amount')
            check.check_date = check_data.get('check_date')
            check.check_number = check_data.get('check_number')
            check.name = check_data.get('name')
            check.address_line1 = check_data.get('address_line1')
            check.address_line2 = check_data.get('address_line2')
            check.city = check_data.get('city')
            check.state = check_data.get('state')
            check.zip_code = check_data.get('zip_code')
            check.is_money_order = check_data.get('is_money_order', False)
            check.needs_review = True
            check.raw_ocr_text = raw_text
            check.check_image_path = check_path
            check.buckslip_image_path = None
            
            db.session.add(check)
            db.session.commit()
            
            check_count += 1
            processing_status[batch_id]['checks_found'] = check_count
    
    def _match_hubspot_contacts(self, batch_id):
        if not self.hubspot.is_configured():
            return
        
        processing_status[batch_id]['message'] = 'Matching HubSpot contacts...'
        
        checks = Check.query.filter_by(batch_id=batch_id).all()
        
        for check in checks:
            if check.name:
                matches = self.hubspot.search_contacts(check.name, check.zip_code)
                
                if matches:
                    best_match = matches[0]
                    check.hubspot_contact_id = best_match['id']
                    check.hubspot_contact_name = best_match['name']
                    check.match_confidence = best_match['confidence']
                    
                    if best_match['confidence'] >= 0.8:
                        check.needs_review = False
        
        db.session.commit()

def get_processing_status(batch_id):
    return processing_status.get(batch_id, {'status': 'unknown'})
