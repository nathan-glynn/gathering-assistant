import re
from typing import Optional, Tuple, Dict, Any, List, BinaryIO
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
import json
import asyncio
import base64
import requests
from functools import lru_cache
from mistralai import Mistral

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
root_dir = Path(__file__).resolve().parent.parent
env_path = root_dir / '.env'
load_dotenv(dotenv_path=env_path)

# Initialize OpenAI API key
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

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

async def process_pdf_for_specifications(pdf_file: bytes, supplier: str, part_numbers: List[str], specifications: List[str]) -> Dict:
    """
    Process a PDF file using OpenAI GPT-4o to extract specifications.
    
    Args:
        pdf_file: The raw PDF file bytes
        supplier: The supplier name
        part_numbers: List of part numbers to look for
        specifications: List of specifications to extract
    
    Returns:
        Dictionary with extracted specifications in the same format as Perplexity API
    """
    try:
        logger.info(f"Processing PDF for {supplier} with part numbers: {part_numbers}")
        
        # Base64 encode the PDF
        pdf_base64 = base64.b64encode(pdf_file).decode('utf-8')
        
        # Create the prompt
        specs_list = "\n".join([f"- {spec}" for spec in specifications])
        parts_list = ", ".join(part_numbers)
        
        prompt = f"""You are an expert data gatherer who prides themselves in gathering the most accurate information from supplier PDF documents. 
You use your industry knowledge to validate information you're gathering makes sense given the context of the products, but ultimately rely on your strong scanning skills of PDF literature and what the supplier's documentations tells you. 
You look at the imbedded text, images, graphs, tables, and charts to intellegently gather values accurately, keeping accuraty paramount as you are compensated as an expert to do this well.

Please gather the following specifications for {supplier} part number(s) {parts_list} from the attached PDF document:

{specs_list}

For each part number and each specification, respond in this exact format:
[Specification Name]  
Value: [exact value or "-" if not found]  
Source: [location in the PDF, e.g., "Page 5, Table 2"]  
Confidence: [High/Medium/Low], [explanation]

Use exactly this format for each specification, with a blank line between specifications.
If a specification is not found, still include it with Value: "-"
"""

        # Create the request payload for GPT-4o vision
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "gpt-4o",
            "messages": [
                {
                    "role": "system", 
                    "content": "You are a technical specialist focused on finding accurate product specifications from supplier PDFs. Only return information for the exact specifications requested, using the exact format specified."
                },
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:application/pdf;base64,{pdf_base64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 4000
        }

        logger.info("Making API request to OpenAI")
        response = await asyncio.to_thread(
            requests.post,
            OPENAI_API_URL,
            headers=headers,
            json=payload,
            timeout=180  # Longer timeout for PDF processing
        )
        
        if response.status_code != 200:
            logger.error(f"OpenAI API error: Status {response.status_code}, Response: {response.text}")
            raise Exception(f"API request failed with status {response.status_code}: {response.text}")

        result = response.json()
        logger.info("OpenAI API call successful")
        
        if 'choices' not in result or not result['choices']:
            logger.error("No choices in response")
            return None
        if 'message' not in result['choices'][0]:
            logger.error("No message in first choice")
            return None
        if 'content' not in result['choices'][0]['message']:
            logger.error("No content in message")
            return None

        raw_response = result['choices'][0]['message']['content']
        
        # Process the response to match Perplexity API format
        processed_results = process_gpt_response(raw_response, part_numbers, specifications)
        return {"results": processed_results}
        
    except Exception as e:
        logger.error(f"Error in process_pdf_for_specifications: {str(e)}")
        return {"error": str(e)}

def process_gpt_response(raw_response: str, part_numbers: List[str], specifications: List[str]) -> List[Dict]:
    """
    Process the GPT-4o response to match the format of Perplexity API
    
    Args:
        raw_response: The raw text response from GPT-4o
        part_numbers: List of part numbers
        specifications: List of specifications
    
    Returns:
        List of dictionaries containing processed specifications
    """
    logger.info(f"Processing GPT response")
    
    all_results = []
    
    for part_number in part_numbers:
        # Extract the section for this part number
        part_section = extract_part_section(raw_response, part_number)
        if not part_section:
            # If no specific section found, assume the entire response is for this part
            # This happens when there's only one part number
            if len(part_numbers) == 1:
                part_section = raw_response
            else:
                logger.warning(f"No section found for part {part_number}")
                continue
        
        # Process the specifications
        spec_results = []
        for spec_name in specifications:
            # Find the section for this specification
            spec_section = extract_spec_section(part_section, spec_name)
            if not spec_section:
                logger.warning(f"No section found for spec {spec_name} in part {part_number}")
                spec_results.append({
                    "name": spec_name,
                    "value": "-",
                    "confidence": 0.0,
                    "validation_status": "grey",
                    "source": {"url": "", "title": "", "confidence_notes": "No results found"},
                    "reasoning": "No results found"
                })
                continue
            
            # Extract value, source, and confidence
            value = extract_value(spec_section)
            source = extract_source(spec_section)
            confidence, reasoning = extract_confidence(spec_section)
            
            # Create a standardized result
            confidence_float = convert_confidence_to_float(confidence)
            validation_status = get_validation_status(confidence_float)
            
            spec_results.append({
                "name": spec_name,
                "value": value,
                "confidence": confidence_float,
                "validation_status": validation_status,
                "source": {
                    "url": source,
                    "title": "PDF Document",
                    "confidence_notes": f"{int(confidence_float * 100)}% confidence from PDF analysis"
                },
                "reasoning": reasoning
            })
        
        all_results.append({
            "part_number": part_number,
            "specifications": spec_results
        })
    
    return all_results

def extract_part_section(text: str, part_number: str) -> str:
    """Extract the section of text related to a specific part number"""
    # This is a simplification - would need to be more robust in practice
    sections = text.split("\n\n\n")
    for section in sections:
        if part_number in section:
            return section
    return text  # Default to returning everything if no specific section found

def extract_spec_section(text: str, spec_name: str) -> str:
    """Extract the section for a specific specification"""
    # Look for the specification header style
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if spec_name.lower() in line.lower() or f"[{spec_name}]" in line or f"**{spec_name}**" in line:
            # Find the end of this section
            for j in range(i+1, len(lines)):
                if any(spec in lines[j] for spec in ["[", "**"]) and ":" not in lines[j]:
                    return "\n".join(lines[i:j])
            # If we reach the end without finding another section
            return "\n".join(lines[i:])
    return ""

def extract_value(spec_section: str) -> str:
    """Extract the value from a specification section"""
    for line in spec_section.split('\n'):
        if "value:" in line.lower():
            return line.split(':', 1)[1].strip()
    return "-"

def extract_source(spec_section: str) -> str:
    """Extract the source from a specification section"""
    for line in spec_section.split('\n'):
        if "source:" in line.lower():
            return line.split(':', 1)[1].strip()
    return ""

def extract_confidence(spec_section: str) -> tuple:
    """Extract confidence level and reasoning from a specification section"""
    for line in spec_section.split('\n'):
        if "confidence:" in line.lower():
            conf_text = line.split(':', 1)[1].strip()
            if ',' in conf_text:
                confidence, reasoning = conf_text.split(',', 1)
                return confidence.strip(), reasoning.strip()
            return conf_text, ""
    return "Low", "No confidence information found"

def convert_confidence_to_float(confidence: str) -> float:
    """Convert a text confidence level to a float"""
    if "high" in confidence.lower():
        return 1.0
    elif "medium" in confidence.lower():
        return 0.7
    elif "low" in confidence.lower():
        return 0.3
    else:
        try:
            # Try to parse a percentage
            return float(confidence.strip('%')) / 100
        except:
            return 0.0

def get_validation_status(confidence: float) -> str:
    """Convert a confidence float to a validation status"""
    if confidence >= 0.8:
        return "green"
    elif confidence >= 0.5:
        return "yellow"
    elif confidence > 0:
        return "red"
    else:
        return "grey"

def parse_ocr_for_specifications(ocr_response, part_numbers, specifications):
    # Combine all markdown text from all pages
    all_text = "\n".join(page["markdown"] if isinstance(page, dict) else page.markdown for page in getattr(ocr_response, 'pages', []))
    results = []
    for part_number in part_numbers:
        part_result = {"part_number": part_number, "specifications": []}
        for spec in specifications:
            # Look for lines like "Spec Name: Value" or "Spec Name - Value"
            pattern = rf"{re.escape(spec)}\s*[:\-]\s*([^\n]+)"
            match = re.search(pattern, all_text, re.IGNORECASE)
            value = match.group(1).strip() if match else "Not found"
            part_result["specifications"].append({
                "name": spec,
                "value": value,
                "source": "OCR"
            })
        results.append(part_result)
    return {"results": results}

def extract_specs_with_llm(ocr_text, part_numbers, specifications, api_key):
    client = Mistral(api_key=api_key)
    # Build the prompt
    prompt = (
        "Extract the following specifications for each part number from the provided text.\n"
        f"Part Numbers: {part_numbers}\n"
        f"Specifications: {specifications}\n"
        "Text:\n"
        f"{ocr_text}\n"
        "Respond in JSON with this format:\n"
        """
        [
          {
            "part_number": "...",
            "specifications": [
              {"name": "...", "value": "..."},
              ...
            ]
          },
          ...
        ]
        """
    )
    # Call Mistral's chat/completion endpoint
    response = client.chat.create(
        model="mistral-large-latest",
        messages=[{"role": "user", "content": prompt}]
    )
    # Extract JSON from the response
    content = response.choices[0].message.content
    # Find the first JSON block in the response
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if match:
        try:
            results = json.loads(match.group(0))
            return {"results": results}
        except Exception:
            pass
    # Fallback: return empty results
    return {"results": []}

def process_pdf_with_mistral(pdf_bytes, supplier, part_numbers, specifications):
    api_key = os.environ["MISTRAL_API_KEY"]
    client = Mistral(api_key=api_key)

    temp_path = "temp_upload.pdf"
    with open(temp_path, "wb") as f:
        f.write(pdf_bytes)

    with open(temp_path, "rb") as f:
        uploaded_pdf = client.files.upload(
            file={
                "file_name": "uploaded_file.pdf",
                "content": f,
            },
            purpose="ocr"
        )
    signed_url = client.files.get_signed_url(file_id=uploaded_pdf.id)
    ocr_response = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": signed_url.url,
        }
    )
    os.remove(temp_path)

    # Combine all markdown text from all pages
    all_text = "\n".join(page["markdown"] if isinstance(page, dict) else page.markdown for page in getattr(ocr_response, 'pages', []))
    # Use LLM to extract specs
    parsed = extract_specs_with_llm(all_text, part_numbers, specifications, api_key)
    # Optionally, include raw OCR for debugging
    pages = getattr(ocr_response, 'pages', [])
    parsed["ocr_debug"] = [p.model_dump() if hasattr(p, 'model_dump') else str(p) for p in pages]
    return parsed 