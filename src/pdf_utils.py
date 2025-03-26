import re
from typing import Optional, Tuple
from functools import lru_cache

@lru_cache(maxsize=1000)
def search_pdf_content(pdf_text: str, part_number: str, specification: str) -> Optional[Tuple[str, float]]:
    """Search PDF content for a specific part number and specification."""
    part_sections = re.split(r'\n\s*\n', pdf_text)
    relevant_sections = []
    
    for section in part_sections:
        if part_number.lower() in section.lower():
            relevant_sections.append(section)
    
    if not relevant_sections:
        return None
    
    spec_pattern = re.compile(rf'{specification}[:\s]+([^\n]+)', re.IGNORECASE)
    
    for section in relevant_sections:
        match = spec_pattern.search(section)
        if match:
            value = match.group(1).strip()
            confidence = 1.0 if part_number in section[:100] else 0.8
            return (value, confidence)
    
    return None 