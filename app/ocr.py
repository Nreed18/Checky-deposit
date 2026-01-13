import re
import pytesseract
from PIL import Image
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

try:
    from onnxtr.io import DocumentFile
    from onnxtr.models import ocr_predictor
    ONNXTR_AVAILABLE = True
except ImportError:
    ONNXTR_AVAILABLE = False

@dataclass
class OCRResult:
    text: str
    confidence: float = 0.0
    word_confidences: List[float] = field(default_factory=list)
    engine: str = 'unknown'
    needs_verification: bool = False

class OCREngine:
    CONFIDENCE_THRESHOLD = 0.75
    
    def __init__(self, use_dual_engine=True):
        self.money_order_keywords = ['money order', 'postal money order', 'usps money order', 'western union']
        self.use_dual_engine = use_dual_engine
        self._predictor = None
        self._onnxtr_available = ONNXTR_AVAILABLE
    
    def _get_predictor(self):
        if self._predictor is None and self._onnxtr_available:
            try:
                self._predictor = ocr_predictor(pretrained=True)
            except Exception as e:
                print(f"Failed to initialize OnnxTR predictor: {e}")
                self._onnxtr_available = False
        return self._predictor
    
    def extract_text(self, image_path) -> str:
        result = self.extract_text_with_confidence(image_path)
        return result.text
    
    def extract_text_with_confidence(self, image_path) -> OCRResult:
        tesseract_result = self._extract_with_tesseract(image_path)
        
        if not self.use_dual_engine or not self._onnxtr_available:
            return tesseract_result
        
        try:
            onnxtr_result = self._extract_with_onnxtr(image_path)
            
            if onnxtr_result.confidence >= self.CONFIDENCE_THRESHOLD:
                return onnxtr_result
            
            # OnnxTR confidence below threshold - use Tesseract as fallback
            # But first compare results to flag disagreements for manual review
            if tesseract_result.text and onnxtr_result.text:
                tesseract_parsed = self.parse_check_data(tesseract_result.text)
                onnxtr_parsed = self.parse_check_data(onnxtr_result.text)
                
                disagreements = self._compare_results(tesseract_parsed, onnxtr_parsed)
                
                if disagreements:
                    # Engines disagree - return Tesseract with both texts for review
                    return OCRResult(
                        text=f"PRIMARY (Tesseract):\n{tesseract_result.text}\n\nSECONDARY (OnnxTR, low confidence):\n{onnxtr_result.text}",
                        confidence=tesseract_result.confidence,
                        engine='dual',
                        needs_verification=True
                    )
            
            # OnnxTR confidence < threshold, fall back to Tesseract
            tesseract_result.needs_verification = True  # Flag since we had to fallback
            return tesseract_result
            
        except Exception as e:
            print(f"OnnxTR Error, using Tesseract result: {e}")
            return tesseract_result
    
    def _compare_results(self, result1: Dict, result2: Dict) -> List[str]:
        disagreements = []
        
        if result1.get('amount') and result2.get('amount'):
            if abs(float(result1['amount']) - float(result2['amount'])) > 0.01:
                disagreements.append('amount')
        
        if result1.get('check_number') != result2.get('check_number'):
            if result1.get('check_number') and result2.get('check_number'):
                disagreements.append('check_number')
        
        name1 = (result1.get('name') or '').lower().strip()
        name2 = (result2.get('name') or '').lower().strip()
        if name1 and name2 and name1 != name2:
            from difflib import SequenceMatcher
            ratio = SequenceMatcher(None, name1, name2).ratio()
            if ratio < 0.7:
                disagreements.append('name')
        
        return disagreements
    
    def _extract_with_onnxtr(self, image_path) -> OCRResult:
        predictor = self._get_predictor()
        if predictor is None:
            raise Exception("OnnxTR predictor not available")
        
        doc = DocumentFile.from_images(image_path)
        result = predictor(doc)
        
        text_lines = []
        all_confidences = []
        
        for page in result.pages:
            for block in page.blocks:
                for line in block.lines:
                    line_words = []
                    for word in line.words:
                        line_words.append(word.value)
                        all_confidences.append(word.confidence)
                    text_lines.append(' '.join(line_words))
        
        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
        
        return OCRResult(
            text='\n'.join(text_lines),
            confidence=avg_confidence,
            word_confidences=all_confidences,
            engine='onnxtr',
            needs_verification=avg_confidence < self.CONFIDENCE_THRESHOLD
        )
    
    def _extract_with_tesseract(self, image_path) -> OCRResult:
        try:
            image = Image.open(image_path)
            text = pytesseract.image_to_string(image)
            
            return OCRResult(
                text=text,
                confidence=0.7,
                engine='tesseract',
                needs_verification=False
            )
        except Exception as e:
            print(f"Tesseract OCR Error: {e}")
            return OCRResult(text='', confidence=0.0, engine='tesseract', needs_verification=True)
    
    def parse_check_data(self, raw_text, is_buckslip=False):
        data = {
            'amount': None,
            'check_date': None,
            'check_number': None,
            'name': None,
            'address_line1': None,
            'address_line2': None,
            'city': None,
            'state': None,
            'zip_code': None,
            'is_money_order': False,
            'raw_ocr_text': raw_text
        }
        
        text_lower = raw_text.lower()
        for keyword in self.money_order_keywords:
            if keyword in text_lower:
                data['is_money_order'] = True
                break
        
        amount_patterns = [
            r'\$\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
            r'\*\*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\*\*',
            r'(\d{1,3}(?:,\d{3})*\.\d{2})\s*(?:dollars|DOLLARS)?',
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, raw_text)
            if match:
                amount_str = match.group(1).replace(',', '')
                try:
                    data['amount'] = float(amount_str)
                    break
                except ValueError:
                    continue
        
        date_patterns = [
            r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})',
            r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{2,4})',
        ]
        for pattern in date_patterns:
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                try:
                    groups = match.groups()
                    if len(groups) == 3:
                        month_val, day_val, year_val = groups[0], groups[1], groups[2]
                        if not str(month_val).isdigit():
                            months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                                     'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
                            month_int = months.get(str(day_val)[:3].lower(), 1)
                            day_int = int(groups[0])
                        else:
                            month_int, day_int = int(month_val), int(day_val)
                        
                        year_int = int(year_val)
                        if year_int < 100:
                            year_int += 2000
                        
                        data['check_date'] = datetime(year_int, month_int, day_int).date()
                        break
                except (ValueError, KeyError):
                    continue
        
        check_num_patterns = [
            r'(?:check\s*#?|no\.?|number)\s*:?\s*(\d{3,10})',
            r'\b(\d{4,10})\b(?=.*(?:check|chk))',
        ]
        for pattern in check_num_patterns:
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                data['check_number'] = match.group(1)
                break
        
        lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
        
        name_found = False
        address_started = False
        
        for i, line in enumerate(lines):
            line_clean = re.sub(r'[^a-zA-Z\s\.,\-\']', '', line).strip()
            
            if not name_found and len(line_clean) > 3:
                words = line_clean.split()
                if 2 <= len(words) <= 5:
                    if all(word[0].isupper() for word in words if word):
                        data['name'] = line_clean
                        name_found = True
                        continue
            
            if name_found and not address_started:
                if re.search(r'\d+\s+\w+', line):
                    data['address_line1'] = line
                    address_started = True
                    continue
            
            if address_started and not data['city']:
                city_state_zip = re.match(r'([A-Za-z\s]+),?\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)', line)
                if city_state_zip:
                    data['city'] = city_state_zip.group(1).strip()
                    data['state'] = city_state_zip.group(2)
                    data['zip_code'] = city_state_zip.group(3)
                elif not data['address_line2']:
                    data['address_line2'] = line
        
        zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\b', raw_text)
        if zip_match and not data['zip_code']:
            data['zip_code'] = zip_match.group(1)
        
        state_match = re.search(r'\b([A-Z]{2})\s+\d{5}', raw_text)
        if state_match and not data['state']:
            data['state'] = state_match.group(1)
        
        return data
    
    def detect_image_type(self, raw_text):
        text_lower = raw_text.lower()
        
        if 'front image - document' in text_lower or 'document front' in text_lower:
            return 'buckslip'
        elif 'front image - check' in text_lower or 'check front' in text_lower:
            return 'check'
        
        check_indicators = ['pay to the order', 'dollars', 'routing', 'account', 'void after']
        buckslip_indicators = ['appeal', 'donation', 'contribution', 'thank you', 'dear']
        
        check_score = sum(1 for ind in check_indicators if ind in text_lower)
        buckslip_score = sum(1 for ind in buckslip_indicators if ind in text_lower)
        
        if check_score > buckslip_score:
            return 'check'
        elif buckslip_score > check_score:
            return 'buckslip'
        
        return 'unknown'
