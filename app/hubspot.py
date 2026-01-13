import requests
from fuzzywuzzy import fuzz
from config import Config

class HubSpotClient:
    def __init__(self):
        self.api_key = Config.HUBSPOT_API_KEY
        self.base_url = "https://api.hubapi.com"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def is_configured(self):
        return bool(self.api_key)
    
    def search_contacts(self, name, zip_code=None):
        if not self.is_configured():
            return []
        
        try:
            name_parts = name.split() if name else []
            firstname = name_parts[0] if name_parts else ""
            lastname = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
            
            filters = []
            if firstname:
                filters.append({
                    "propertyName": "firstname",
                    "operator": "CONTAINS_TOKEN",
                    "value": firstname
                })
            
            search_payload = {
                "filterGroups": [{"filters": filters}] if filters else [],
                "properties": ["firstname", "lastname", "address", "city", "state", "zip", "email"],
                "limit": 20
            }
            
            response = requests.post(
                f"{self.base_url}/crm/v3/objects/contacts/search",
                headers=self.headers,
                json=search_payload,
                timeout=10
            )
            
            if response.status_code == 200:
                results = response.json().get('results', [])
                return self._score_matches(results, name, zip_code)
            else:
                print(f"HubSpot search error: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            print(f"HubSpot API error: {e}")
            return []
    
    def _score_matches(self, contacts, search_name, search_zip):
        scored_contacts = []
        
        for contact in contacts:
            props = contact.get('properties', {})
            
            contact_name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
            
            name_score = fuzz.ratio(search_name.lower(), contact_name.lower()) / 100.0 if search_name and contact_name else 0
            
            zip_score = 1.0 if search_zip and props.get('zip') == search_zip else 0.5
            
            combined_score = (name_score * 0.7) + (zip_score * 0.3)
            
            scored_contacts.append({
                'id': contact.get('id'),
                'name': contact_name,
                'email': props.get('email', ''),
                'address': props.get('address', ''),
                'city': props.get('city', ''),
                'state': props.get('state', ''),
                'zip': props.get('zip', ''),
                'confidence': round(combined_score, 2)
            })
        
        scored_contacts.sort(key=lambda x: x['confidence'], reverse=True)
        return scored_contacts
    
    def create_deal(self, check_data, contact_id, appeal_code):
        if not self.is_configured():
            return None
        
        try:
            amount = float(check_data.get('amount', 0))
            name = check_data.get('name', 'Unknown')
            
            deal_payload = {
                "properties": {
                    "dealname": f"Donation - ${amount:.2f} - {name}",
                    "amount": str(amount),
                    "dealstage": "closedwon",
                    "pipeline": "default",
                    "closedate": check_data.get('check_date', ''),
                    "description": f"Appeal Code: {appeal_code}\nCheck #: {check_data.get('check_number', 'N/A')}"
                }
            }
            
            response = requests.post(
                f"{self.base_url}/crm/v3/objects/deals",
                headers=self.headers,
                json=deal_payload,
                timeout=10
            )
            
            if response.status_code == 201:
                deal = response.json()
                deal_id = deal.get('id')
                
                if contact_id:
                    self._associate_deal_to_contact(deal_id, contact_id)
                
                return deal_id
            else:
                print(f"Deal creation error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Deal creation error: {e}")
            return None
    
    def _associate_deal_to_contact(self, deal_id, contact_id):
        try:
            response = requests.put(
                f"{self.base_url}/crm/v3/objects/deals/{deal_id}/associations/contacts/{contact_id}/deal_to_contact",
                headers=self.headers,
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Association error: {e}")
            return False
    
    def get_contact(self, contact_id):
        if not self.is_configured():
            return None
        
        try:
            response = requests.get(
                f"{self.base_url}/crm/v3/objects/contacts/{contact_id}",
                headers=self.headers,
                params={"properties": "firstname,lastname,email,address,city,state,zip"},
                timeout=10
            )
            
            if response.status_code == 200:
                contact = response.json()
                props = contact.get('properties', {})
                return {
                    'id': contact.get('id'),
                    'name': f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
                    'email': props.get('email', ''),
                    'address': props.get('address', ''),
                    'city': props.get('city', ''),
                    'state': props.get('state', ''),
                    'zip': props.get('zip', '')
                }
            return None
        except Exception as e:
            print(f"Get contact error: {e}")
            return None
