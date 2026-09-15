import re
from typing import Optional, Dict, Any, List, Tuple

# Normalization regular expressions
COMPANY_CLEAN_REGEX = re.compile(
    r'\s*[\(\[-]\s*(new client|new customer|test client|test|unknown|customer|na|n/a|prospect|lead|exports?|imports?|domestic|overseas)\s*[\)\]-]?\s*',
    re.IGNORECASE
)

SALUTATION_REGEX = re.compile(
    r'^\s*(mr\.?|mrs\.?|ms\.?|miss\.?|dr\.?)\s+',
    re.IGNORECASE
)

HONORIFIC_SUFFIX_REGEX = re.compile(
    r'\s+ji\s*$',
    re.IGNORECASE
)

DESIGNATION_KEYWORDS = (
    'manager', 'director', 'ceo', 'cfo', 'coo', 'vp', 'executive', 'sales', 'rep', 
    'lead', 'partner', 'assistant', 'asst', 'supervisor', 'supv', 'coordinator', 
    'coord', 'mgr', 'head', 'owner', 'proprietor', 'import', 'export', 'logistics'
)

INDIAN_CITIES_STATES = {
    'new delhi': ('New Delhi', 'Delhi'),
    'delhi': ('Delhi', 'Delhi'),
    'mumbai': ('Mumbai', 'Maharashtra'),
    'bombay': ('Mumbai', 'Maharashtra'),
    'chennai': ('Chennai', 'Tamil Nadu'),
    'madras': ('Chennai', 'Tamil Nadu'),
    'kolkata': ('Kolkata', 'West Bengal'),
    'calcutta': ('Kolkata', 'West Bengal'),
    'bangalore': ('Bangalore', 'Karnataka'),
    'bengaluru': ('Bangalore', 'Karnataka'),
    'hyderabad': ('Hyderabad', 'Telangana'),
    'pune': ('Pune', 'Maharashtra'),
    'gurgaon': ('Gurgaon', 'Haryana'),
    'gurugram': ('Gurugram', 'Haryana'),
    'noida': ('Noida', 'Uttar Pradesh'),
    'ghaziabad': ('Ghaziabad', 'Uttar Pradesh'),
    'faridabad': ('Faridabad', 'Haryana')
}

MIDDLE_EAST_COUNTRIES = {'uae', 'united arab emirates', 'saudi arabia', 'saudi', 'qatar', 'oman', 'kuwait', 'bahrain', 'yemen'}

def normalize_company_name(raw_name: str) -> str:
    if not raw_name:
        return ""
    name = str(raw_name).strip()
    name_clean = COMPANY_CLEAN_REGEX.sub(" ", name).strip()
    name_clean = " ".join(name_clean.split())
    return name_clean if name_clean else name

def normalize_contact_name(raw_name: str) -> str:
    if not raw_name:
        return ""
    name = re.sub(r'[\*\_\~\#]', '', str(raw_name)).strip()
    name_clean = re.sub(r'\b(mr|mrs|ms|miss|dr|shri|smt|mam|maam|ji)\b\.?', '', name, flags=re.IGNORECASE).strip()
    name_clean = " ".join(name_clean.split())
    return name_clean if name_clean else name

def clean_designation_cell(val: str) -> Optional[str]:
    if not val:
        return None
    val_str = str(val).strip()
    val_lower = val_str.lower()
    
    if not any(k in val_lower for k in DESIGNATION_KEYWORDS):
        return None
        
    parentheses_blocks = re.findall(r'\((.*?)\)', val_str)
    for block in parentheses_blocks:
        block_clean = block.strip()
        block_lower = block_clean.lower()
        if any(keyword in block_lower for keyword in DESIGNATION_KEYWORDS):
            return " ".join(block_clean.split())
            
    parts = [p.strip() for p in re.split(r'[-/,\n\r]', val_str) if p.strip()]
    for p in parts:
        p_lower = p.lower()
        if any(keyword in p_lower for keyword in DESIGNATION_KEYWORDS):
            return p
            
    return val_str

def extract_designation_v2(name_cell: str) -> Optional[str]:
    if not name_cell:
        return None
    text_str = str(name_cell).strip()
    parentheses_blocks = re.findall(r'\((.*?)\)', text_str)
    for block in parentheses_blocks:
        block_clean = block.strip()
        block_lower = block_clean.lower()
        if any(keyword in block_lower for keyword in DESIGNATION_KEYWORDS):
            if "new client" not in block_lower and "new customer" not in block_lower:
                block_clean = re.sub(r'\s*-\s*', ' - ', block_clean)
                return " ".join(block_clean.split())
    parts = [p.strip() for p in re.split(r'[-/,\n\r]', text_str) if p.strip()]
    for p in parts:
        p_lower = p.lower()
        if any(keyword in p_lower for keyword in DESIGNATION_KEYWORDS):
            if "new client" not in p_lower and "new customer" not in p_lower:
                return p
    return None

def split_primary_contact(text: str) -> tuple[str, Optional[str]]:
    if not text:
        return "", None
    text_str = str(text).strip()
    
    m = re.match(r'^([^\(]+)\(([^\)]+)\)\s*$', text_str)
    if m:
        name_part = m.group(1).strip()
        desc_part = m.group(2).strip()
        if any(k in desc_part.lower() for k in DESIGNATION_KEYWORDS):
            name_clean = normalize_contact_name(name_part)
            if any(sep in name_clean.lower() for sep in (' & ', ' and ', ' / ', ' ; ')):
                parts = re.split(r'\s*;\s*|\s*&\s*|\s+and\s+|\s*/\s*', name_clean, flags=re.IGNORECASE)
                name_clean = normalize_contact_name(parts[0])
            return name_clean, desc_part
            
    parts = re.split(r'\s*;\s*|\s*&\s*|\s+and\s+|\s*/\s*', text_str, flags=re.IGNORECASE)
    primary_part = parts[0].strip()
    
    designation = extract_designation_v2(primary_part)
    if not designation and len(parts) > 1:
        for p in parts[1:]:
            designation = extract_designation_v2(p)
            if designation:
                break
                
    name_clean = re.sub(r'\(.*?\)', '', primary_part).strip()
    name_clean = re.sub(r'\s*-\s*.*$', '', name_clean).strip()
    name_clean = normalize_contact_name(name_clean)
    
    if designation:
        designation_esc = re.escape(designation)
        name_clean = re.sub(designation_esc, '', name_clean, flags=re.IGNORECASE).strip()
        name_clean = re.sub(r'\s*-\s*$', '', name_clean).strip()
        name_clean = re.sub(r'\s*,\s*$', '', name_clean).strip()
        
    return name_clean, designation

def parse_location(text: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    if not text:
        return None, None, None, None
    text_str = str(text).strip()
    text_lower = text_str.lower()
    
    common_countries = {'india', 'china', 'germany', 'usa', 'united states', 'japan', 'italy', 'vietnam', 'malaysia'}
    if text_lower in common_countries:
        country_resolved = text_str
        if country_lower := country_resolved.lower() in ('usa', 'us', 'united states'):
            country_resolved = "USA"
        elif country_lower == 'china':
            country_resolved = "China"
        elif country_lower == 'india':
            country_resolved = "India"
        return None, None, None, country_resolved
        
    parts = [p.strip() for p in text_str.split(',') if p.strip()]
    city = None
    state = None
    country = None
    address = text_str
    
    inferred_india = False
    for key, (ct, st) in INDIAN_CITIES_STATES.items():
        if re.search(r'\b' + re.escape(key) + r'\b', text_lower):
            city = ct
            state = st
            inferred_india = True
            break
            
    if 'india' in text_lower or inferred_india:
        country = 'India'
    elif 'china' in text_lower:
        country = 'China'
    elif 'usa' in text_lower or 'united states' in text_lower:
        country = 'USA'
        
    if len(parts) == 1 and not inferred_india and not any(k in text_lower for k in ('road', 'street', 'marg', 'building', 'house', 'floor', 'zone', 'sector')):
        return None, None, None, text_str
        
    return address, city, state, country

def normalize_email(raw_email: str) -> Optional[str]:
    if not raw_email:
        return None
    email_str = str(raw_email).strip().lower()
    return email_str if email_str else None

def validate_email_syntax(email_val: Optional[str]) -> Tuple[bool, Optional[str]]:
    """
    Strict email syntax validation.
    Returns (is_valid: bool, error_message: Optional[str]).
    
    Checks:
    - Non-empty
    - Standard RFC 5322 structure via email-validator (or strict fallback regex)
    - Valid TLD (not .con, .comm, .conn, etc.)
    - No double dots in domain
    - No whitespace in original or normalized email
    """
    if not email_val:
        return False, "Email address is missing or empty"
        
    email_str = str(email_val).strip()
    
    if re.search(r'\s', email_str):
        return False, "Email contains invalid whitespace"
        
    if ".." in email_str:
        return False, "Email domain or address contains double dots"
        
    if email_str.endswith('.'):
        return False, "Email contains trailing dot"

    # Known invalid/typo TLDs to explicitly reject (including common typos like .con, .comm, .conn, .co, .coom, etc.)
    invalid_tlds = {"con", "comm", "conn", "coom", "cm", "cmo", "co"}
    parts = email_str.rsplit(".", 1)
    if len(parts) == 2:
        tld = parts[1].lower()
        if tld in invalid_tlds:
            return False, f"Email contains invalid or suspicious top-level domain (.{tld})"


    try:
        from email_validator import validate_email as ev_validate, EmailNotValidError
        # Check syntax strictly without DNS/MX lookup for speed and stability
        ev_validate(email_str, check_deliverability=False)
        return True, None
    except ImportError:
        pass
    except Exception as e:
        return False, f"Invalid email syntax: {str(e)}"

    # Strict fallback regex if email-validator is not installed/working
    # Requires standard local part, single @, valid domain, valid TLD (2+ alpha chars)
    strict_pattern = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    if not strict_pattern.match(email_str):
        return False, "Invalid email syntax"

    return True, None


def normalize_phone(raw_phone: str) -> Optional[str]:
    if not raw_phone:
        return None
    phone_str = str(raw_phone).strip()
    
    digits_only = re.sub(r'\D', '', phone_str)
    if len(digits_only) == 20:
        part1 = digits_only[:10]
        part2 = digits_only[10:]
        if part1[0] in '6789' and part2[0] in '6789':
            return part1
            
    if len(digits_only) == 22 and digits_only.startswith('91'):
        part1 = digits_only[2:12]
        part2 = digits_only[12:22]
        if part1[0] in '6789' and part2[0] in '6789':
            return part1
 
    parts = re.split(r'\s*[\&\/\,\;\s]\s*', phone_str)
    for part in parts:
        cleaned = re.sub(r'[^\d+]', '', part)
        if len(cleaned) >= 7:
            return cleaned
 
    phone_clean = re.sub(r'[^\d+]', '', phone_str)
    if len(phone_clean) >= 7:
        return phone_clean
    return None

def normalize_website(raw_web: str) -> Optional[str]:
    if not raw_web:
        return None
    web_str = str(raw_web).strip().lower()
    if web_str.startswith('www.') or web_str.startswith('http://') or web_str.startswith('https://'):
        return web_str
    if '.' in web_str and len(web_str) > 4:
        return web_str
    return None

def normalize_shipment_mode(raw_mode: str) -> Optional[str]:
    if not raw_mode:
        return None
    mode_str = str(raw_mode).strip().lower()
    has_air = 'air' in mode_str
    has_sea = 'sea' in mode_str or 'ocean' in mode_str
    has_road = 'road' in mode_str or 'truck' in mode_str
    has_rail = 'rail' in mode_str
    
    modes = []
    if has_air: modes.append('air')
    if has_sea: modes.append('sea')
    if has_road: modes.append('road')
    if has_rail: modes.append('rail')
    
    if len(modes) > 1:
        return 'multi'
    elif len(modes) == 1:
        return modes[0]
    return None

def normalize_trade_direction(raw_dir: str) -> Optional[str]:
    if not raw_dir:
        return None
    dir_str = str(raw_dir).strip().lower()
    if ('import' in dir_str and 'export' in dir_str) or ('imp' in dir_str and 'exp' in dir_str):
        return 'both'
    if 'import' in dir_str or 'imp' in dir_str:
        return 'import'
    if 'export' in dir_str or 'exp' in dir_str:
        return 'export'
    return None

def normalize_country(raw_country: str) -> Optional[str]:
    if not raw_country:
        return None
    val = str(raw_country).strip()
    return val if val else None

def derive_trade_region(country: Optional[str]) -> Optional[str]:
    if not country:
        return None
    country_lower = country.strip().lower()
    if country_lower in ('china', 'prc'):
        return 'china'
    if country_lower in MIDDLE_EAST_COUNTRIES:
        return 'middle_east'
    if country_lower in ('germany', 'italy', 'france', 'uk', 'united kingdom', 'europe'):
        return 'europe'
    if country_lower in ('japan', 'korea', 'south korea', 'taiwan'):
        return 'east_asia'
    if country_lower in ('usa', 'us', 'united states', 'canada', 'mexico'):
        return 'north_america'
    return 'other'
