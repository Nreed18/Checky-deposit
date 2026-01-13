import os
import threading
from pdf2image import convert_from_path
from PIL import Image
from app import db
from app.models import Batch, Check
from app.ocr import OCREngine
from app.hubspot import HubSpotClient

processing_status = {}
status_lock = threading.Lock()

def update_status(batch_id, updates):
    with status_lock:
        if batch_id not in processing_status:
            processing_status[batch_id] = {}
        processing_status[batch_id].update(updates)

def get_status(batch_id):
    with status_lock:
        return dict(processing_status.get(batch_id, {'status': 'unknown'}))

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
                update_status(batch_id, {
                    'status': 'converting',
                    'current_page': 0,
                    'total_pages': 0,
                    'checks_found': 0,
                    'message': 'Converting PDF to images...'
                })
                
                images = convert_from_path(pdf_path, dpi=300)
                total_pages = len(images)
                
                update_status(batch_id, {'total_pages': total_pages, 'status': 'processing'})
                
                batch = db.session.get(Batch, batch_id)
                if not batch:
                    update_status(batch_id, {'status': 'error', 'message': 'Batch not found'})
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
                    
                    update_status(batch_id, {
                        'status': 'complete',
                        'total_pages': total_pages,
                        'checks_found': batch.total_checks,
                        'message': 'Processing complete!'
                    })
                else:
                    update_status(batch_id, {
                        'status': 'error',
                        'total_pages': total_pages,
                        'checks_found': 0,
                        'message': 'Batch not found after processing'
                    })
                
            except Exception as e:
                print(f"Processing error: {e}")
                update_status(batch_id, {
                    'status': 'error',
                    'message': str(e)
                })
                
                batch = db.session.get(Batch, batch_id)
                if batch:
                    batch.status = 'error'
                    db.session.commit()
    
    def _process_bank_batch(self, batch_id, images, image_dir):
        update_status(batch_id, {
            'message': 'Classifying pages...'
        })
        
        classified_pages = []
        for page_num, image in enumerate(images):
            update_status(batch_id, {
                'current_page': page_num + 1,
                'message': f'Classifying page {page_num + 1} of {len(images)}...'
            })
            
            temp_path = os.path.join(image_dir, f'page_{page_num + 1}_temp.png')
            image.save(temp_path, 'PNG')
            raw_text = self.ocr.extract_text(temp_path)
            
            image_type = self.ocr.detect_image_type(raw_text)
            
            classified_pages.append({
                'page_num': page_num + 1,
                'type': image_type,
                'image': image,
                'temp_path': temp_path,
                'raw_text': raw_text
            })
        
        update_status(batch_id, {
            'message': 'Pairing checks with buck slips...'
        })
        
        check_count = 0
        i = 0
        while i < len(classified_pages):
            page_info = classified_pages[i]
            
            if page_info['type'] == 'check':
                check_page = page_info
                buckslip_page = None
                
                for j in range(i + 1, len(classified_pages)):
                    if classified_pages[j]['type'] == 'buckslip':
                        buckslip_page = classified_pages[j]
                        i = j
                        break
                
                check_path = os.path.join(image_dir, f'page_{check_page["page_num"]}_check.png')
                os.rename(check_page['temp_path'], check_path)
                check_text = check_page['raw_text']
                check_data = self.ocr.parse_check_data(check_text, is_buckslip=False)
                
                buckslip_path = None
                buckslip_text = ""
                buckslip_data = {}
                
                if buckslip_page:
                    buckslip_path = os.path.join(image_dir, f'page_{buckslip_page["page_num"]}_buckslip.png')
                    os.rename(buckslip_page['temp_path'], buckslip_path)
                    buckslip_text = buckslip_page['raw_text']
                    buckslip_data = self.ocr.parse_check_data(buckslip_text, is_buckslip=True)
                
                check = Check()
                check.batch_id = batch_id
                check.page_number = check_page['page_num']
                check.amount = check_data.get('amount')
                check.check_date = check_data.get('check_date')
                check.check_number = check_data.get('check_number')
                check.name = buckslip_data.get('name') if buckslip_data else check_data.get('name')
                check.address_line1 = buckslip_data.get('address_line1') if buckslip_data else check_data.get('address_line1')
                check.address_line2 = buckslip_data.get('address_line2') if buckslip_data else check_data.get('address_line2')
                check.city = buckslip_data.get('city') if buckslip_data else check_data.get('city')
                check.state = buckslip_data.get('state') if buckslip_data else check_data.get('state')
                check.zip_code = buckslip_data.get('zip_code') if buckslip_data else check_data.get('zip_code')
                check.is_money_order = check_data.get('is_money_order', False)
                check.needs_review = True
                check.raw_ocr_text = f"CHECK (page {check_page['page_num']}):\n{check_text}\n\nBUCKSLIP (page {buckslip_page['page_num'] if buckslip_page else 'N/A'}):\n{buckslip_text}"
                check.check_image_path = check_path
                check.buckslip_image_path = buckslip_path
                
                db.session.add(check)
                db.session.commit()
                
                check_count += 1
                update_status(batch_id, {'checks_found': check_count})
            
            i += 1
    
    def _process_mail_batch(self, batch_id, images, image_dir):
        check_count = 0
        
        for page_num, image in enumerate(images):
            update_status(batch_id, {
                'current_page': page_num + 1,
                'message': f'Processing page {page_num + 1} of {len(images)}...'
            })
            
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
            update_status(batch_id, {'checks_found': check_count})
    
    def _match_hubspot_contacts(self, batch_id):
        if not self.hubspot.is_configured():
            return
        
        update_status(batch_id, {'message': 'Matching HubSpot contacts...'})
        
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
    return get_status(batch_id)
