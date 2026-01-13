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

        # Debug logging - print first 800 chars of OCR text
        print(f"\n{'='*60}")
        print(f"PARSING {'BUCKSLIP' if is_buckslip else 'CHECK'}")
        print(f"{'='*60}")
        print(f"RAW TEXT:\n{raw_text[:800]}")
        print(f"{'='*60}\n")

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

        # Improved check number extraction - avoid metadata fields
        # Metadata keywords that indicate this is NOT a check number
        metadata_keywords = ['lockbox', 'transaction', 'batch', 'sequence', 'deposit date', 'site code']

        if not is_buckslip:
            # For checks, prioritize shorter check numbers (3-4 digits are most common)
            # and avoid lines containing metadata keywords
            check_num_patterns = [
                # Check number explicitly labeled, but not preceded by metadata keywords
                r'(?<!lockbox\s)(?<!transaction\s)(?<!batch\s)(?<!sequence\s)(?:check\s*#?|check\s+no\.?)\s*:?\s*(\d{3,4})\b',
                # 3-4 digit number at start of line or after whitespace (typical check number position)
                r'(?:^|\s)(\d{3,4})(?:\s|$)',
            ]

            for pattern in check_num_patterns:
                matches = list(re.finditer(pattern, raw_text, re.IGNORECASE))
                for match in matches:
                    # Get surrounding context to verify it's not metadata
                    start_pos = max(0, match.start() - 50)
                    end_pos = min(len(raw_text), match.end() + 50)
                    context = raw_text[start_pos:end_pos].lower()

                    # Skip if metadata keywords are nearby
                    if any(keyword in context for keyword in metadata_keywords):
                        continue

                    # This looks like a real check number
                    potential_number = match.group(1)
                    # Prefer 3-4 digit numbers
                    if 3 <= len(potential_number) <= 4:
                        data['check_number'] = potential_number
                        break

                if data['check_number']:
                    break

        lines = [line.strip() for line in raw_text.split('\n') if line.strip()]

        # Metadata keywords to exclude from name/address extraction
        metadata_exclusions = ['batch', 'report', 'detail', 'lockbox', 'transaction',
                               'deposit', 'sequence', 'site code', 'appeal', 'page', ' of ']

        # Street suffixes that indicate an address, not a name
        street_suffixes = ['street', 'st', 'road', 'rd', 'avenue', 'ave', 'boulevard', 'blvd',
                          'drive', 'dr', 'lane', 'ln', 'court', 'ct', 'circle', 'cir',
                          'way', 'place', 'pl', 'terrace', 'ter', 'po box', 'p.o. box',
                          'box', 'suite', 'ste', 'apartment', 'apt', 'unit']

        # Organization keywords that indicate this is NOT a person's name
        # NOTE: 'trust' and 'fund' are NOT included because they can be legitimate donor names
        # (e.g., "John Smith Family Trust" or "Smith Foundation Fund")
        organization_keywords = ['family', 'radio', 'church', 'ministry', 'foundation',
                                'organization', 'charity', 'inc', 'llc', 'corp', 'company',
                                'association', 'society', 'bank', 'fargo', 'wells', 'union', 'credit']

        name_found = False
        address_started = False

        for i, line in enumerate(lines):
            line_lower = line.lower()

            # Skip lines that contain metadata keywords
            if any(keyword in line_lower for keyword in metadata_exclusions):
                continue

            line_clean = re.sub(r'[^a-zA-Z\s\.,\-\']', '', line).strip()

            # Name extraction - prioritize names that appear before addresses
            if not name_found and len(line_clean) > 3:
                words = line_clean.split()

                # Check if line contains organization keywords - extract name BEFORE them
                # Example: "Carl Augustine Family Radio" -> extract "Carl Augustine"
                potential_name = None
                words_lower = line_lower.split()
                org_found_at = -1
                for idx, word in enumerate(words_lower):
                    if word in organization_keywords:
                        org_found_at = idx
                        break

                if org_found_at > 0:
                    # Extract words before organization keyword
                    name_words = words[:org_found_at]
                    if 2 <= len(name_words) <= 5:
                        potential_name = ' '.join(name_words)
                elif 2 <= len(words) <= 5:
                    # No org keywords found, use whole line
                    potential_name = line_clean

                if potential_name:
                    # Check if all words start with uppercase (typical name format)
                    name_words_check = potential_name.split()
                    if all(word[0].isupper() for word in name_words_check if word):
                        # Exclude street addresses
                        potential_lower = potential_name.lower()
                        has_street_suffix = any(suffix in potential_lower for suffix in street_suffixes)
                        # Exclude generic terms
                        generic_terms = ['dear', 'thank', 'please', 'enclosed']
                        has_generic = any(term in potential_lower for term in generic_terms)

                        if not has_street_suffix and not has_generic:
                            # Check if this line or next few lines have an address
                            is_before_address = False
                            for j in range(i + 1, min(i + 4, len(lines))):
                                next_line = lines[j].lower()
                                # Check if next line looks like an address
                                if re.search(r'\d+\s+[A-Za-z]', lines[j]) and any(suffix in next_line for suffix in street_suffixes):
                                    is_before_address = True
                                    break

                            if is_before_address:
                                # This is likely a donor name (appears before address)
                                data['name'] = potential_name
                                name_found = True
                                continue
                            elif not data['name']:
                                # Store as potential name even if not before address
                                data['name'] = potential_name

            # Address extraction - look for street address with number
            if not address_started:
                # Street address pattern: number followed by street name with suffix
                if re.search(r'\d+\s+[A-Za-z]', line):
                    # Must have a street suffix to be considered an address
                    has_street_suffix = any(suffix in line_lower for suffix in street_suffixes)
                    # Exclude metadata patterns
                    has_metadata = re.search(r'(#\s*:|lockbox|transaction|batch|sequence|page\s+\d)', line, re.IGNORECASE)

                    if has_street_suffix and not has_metadata:
                        # Clean address: extract only the street part, remove trailing numbers/codes
                        # Pattern: number + street name + suffix (stop at extra numbers or multiple digits)
                        addr_match = re.match(r'(\d+\s+[A-Za-z\s\.]+?(?:' + '|'.join(street_suffixes) + r')\.?)\s*(?:\d|$)', line, re.IGNORECASE)
                        if addr_match:
                            data['address_line1'] = addr_match.group(1).strip()
                        else:
                            # Fallback: just use the line as is
                            data['address_line1'] = line
                        address_started = True
                        continue

            # City, State, ZIP extraction - look for pattern in current line
            if address_started and not data['city']:
                # Try to match "City, ST 12345" or "City ST 12345"
                city_state_zip = re.search(r'([A-Za-z\s]+),?\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)', line)
                if city_state_zip:
                    data['city'] = city_state_zip.group(1).strip()
                    data['state'] = city_state_zip.group(2)
                    data['zip_code'] = city_state_zip.group(3)
                # Skip page numbers and other metadata for address_line2
                elif not re.search(r'page\s+\d+|of\s+\d+', line, re.IGNORECASE):
                    if not data['address_line2']:
                        data['address_line2'] = line

        # Extract city/state/zip from anywhere in the text if not found yet
        if not data['city'] or not data['state'] or not data['zip_code']:
            # Look for city, state, zip pattern anywhere
            city_state_zip_match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),?\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)', raw_text)
            if city_state_zip_match:
                if not data['city']:
                    data['city'] = city_state_zip_match.group(1).strip()
                if not data['state']:
                    data['state'] = city_state_zip_match.group(2)
                if not data['zip_code']:
                    data['zip_code'] = city_state_zip_match.group(3)

        # Fallback: extract zip and state separately if still not found
        if not data['zip_code']:
            zip_match = re.search(r'\b(\d{5}(?:-\d{4})?)\b', raw_text)
            if zip_match:
                data['zip_code'] = zip_match.group(1)

        if not data['state']:
            state_match = re.search(r'\b([A-Z]{2})\s+\d{5}', raw_text)
            if state_match:
                data['state'] = state_match.group(1)

        # Debug logging - show extracted fields
        print(f"EXTRACTED FIELDS:")
        print(f"  Check Number: {data['check_number']}")
        print(f"  Name: {data['name']}")
        print(f"  Address Line 1: {data['address_line1']}")
        print(f"  City: {data['city']}")
        print(f"  State: {data['state']}")
        print(f"  ZIP: {data['zip_code']}")
        print(f"{'='*60}\n")

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
