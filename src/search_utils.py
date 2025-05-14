from typing import Dict, Any, List
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
import json
import asyncio
import aiohttp
import ssl
import certifi
import requests
from concurrent.futures import ThreadPoolExecutor

# Debugging feature
import time
import psutil

start_ts = time.perf_counter()  # used to track elapsed time

def log_stage(stage: str):
    process = psutil.Process(os.getpid())
    mem = process.memory_info().rss / 1024 / 1024
    now = time.perf_counter()
    logger.info(f"[{stage}] Time elapsed: {now - start_ts:.2f}s | Memory: {mem:.2f} MB")

# Load environment variables
root_dir = Path(__file__).resolve().parent.parent
env_path = root_dir / '.env'
load_dotenv(dotenv_path=env_path)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Perplexity API key
PERPLEXITY_API_KEY = os.getenv('PERPLEXITY_API_KEY')
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"

async def get_specification_async(supplier: str, part_number: str, specifications: List[str]) -> Dict:
    try:
        specs_list = "\n".join([f"- {spec}" for spec in specifications])
        prompt = f"""Please gather the following specifications for {supplier} part number {part_number}:

{specs_list}

For each specification, respond in this exact format:
[Specification Name]
Value: [exact value or "-" if not found]
Source: [URL or document name]
Confidence: [High/Medium/Low], [explanation]

Use exactly this format for each specification, with a blank line between specifications.
If a specification is not found, still include it with Value: "-"

Please be thorough but concise in your response. Only provide information for the specifications listed above."""

        logger.info(f"Making Perplexity API call for {supplier} part {part_number}")
        try:
            headers = {
                "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "sonar-pro",
                "messages": [
                    {"role": "system", "content": "You are a technical specialist focused on finding accurate product specifications from reliable sources. Only return information for the exact specifications requested, using the exact format specified."},
                    {"role": "user", "content": prompt}
                ]
            }

            logger.info("Making API request to Perplexity")
            response = await asyncio.to_thread(
                requests.post,
                PERPLEXITY_API_URL,
                headers=headers,
                json=payload,
                timeout=30
            )
        except requests.exceptions.Timeout:
            logger.error(f"Timeout occurred for part {part_number}")
            return None
        except Exception as api_error:
            logger.error(f"Perplexity API error: {str(api_error)}")
            return None

        if response.status_code != 200:
            logger.error(f"Perplexity API error: Status {response.status_code}, Response: {response.text}")
            logger.error(f"Request headers: {headers}")
            raise Exception(f"API request failed with status {response.status_code}: {response.text}")

        result = response.json()
        logger.info(f"Perplexity API raw response: {json.dumps(result, indent=2)}")
        logger.info("Perplexity API call successful")

        if 'choices' not in result or not result['choices']:
            logger.error("No choices in response")
            return None
        if 'message' not in result['choices'][0]:
            logger.error("No message in first choice")
            return None
        if 'content' not in result['choices'][0]['message']:
            logger.error("No content in message")
            return None

        return result['choices'][0]['message']['content']

    except Exception as e:
        logger.error(f"Error in get_specification_async: {str(e)}")
        return None

def process_response(raw_response: str, specifications: List[str]) -> Dict[str, Any]:
    logger.info(f"Processing raw response: {raw_response}")
    sections = [s.strip() for s in raw_response.split('\n\n') if s.strip()]
    logger.info(f"Found {len(sections)} sections")
    processed_specs = {}

    for spec in specifications:
        logger.info(f"Processing specification: {spec}")
        for section in sections:
            if section.lower().startswith(spec.lower()) or spec.lower() in section.lower().split('\n')[0]:
                logger.info(f"Found matching section for {spec}: {section}")
                lines = section.split('\n')
                value = "-"
                source_url = ""
                source_notes = ""
                reasoning = ""

                for line in lines:
                    line = line.strip()
                    if line.lower().startswith('value:'):
                        value = line.split(':', 1)[1].strip()
                        logger.info(f"Found value: {value}")
                    elif line.lower().startswith('source:'):
                        source_url = line.split(':', 1)[1].strip()
                        logger.info(f"Found source: {source_url}")
                    elif line.lower().startswith('confidence:'):
                        conf_text = line.split(':', 1)[1].strip()
                        if ',' in conf_text:
                            reasoning = conf_text.split(',', 1)[1].strip()
                            source_notes = reasoning
                            logger.info(f"Found confidence reasoning: {reasoning}")

                if spec not in processed_specs:
                    processed_specs[spec] = []
                if value != "-":
                    processed_specs[spec].append({
                        "value": value,
                        "source": source_url,
                        "reasoning": reasoning
                    })
                    logger.info(f"Added specification result for {spec}")
                break

    logger.info(f"Final processed specs: {json.dumps(processed_specs, indent=2)}")
    return processed_specs

def calculate_confidence(spec_results: List[Dict]) -> Dict:
    if not spec_results:
        return {
            "value": "-",
            "confidence": 0.0,
            "validation_status": "grey",
            "source": {"url": "", "title": "", "confidence_notes": "No results found"},
            "reasoning": "No results found"
        }

    value_counts = {}
    for result in spec_results:
        value = result["value"]
        if value in value_counts:
            value_counts[value]["count"] += 1
            value_counts[value]["sources"].append(result["source"])
            value_counts[value]["reasoning"].append(result["reasoning"])
        else:
            value_counts[value] = {
                "count": 1,
                "sources": [result["source"]],
                "reasoning": [result["reasoning"]]
            }

    most_common = max(value_counts.items(), key=lambda x: x[1]["count"])
    value, details = most_common
    confidence = details["count"] / len(spec_results)

    if confidence == 1.0:
        validation_status = "green"
    elif confidence >= 0.66:
        validation_status = "yellow"
    else:
        validation_status = "red"

    return {
        "value": value,
        "confidence": confidence,
        "validation_status": validation_status,
        "source": {
            "url": details["sources"][0],
            "title": "Multiple Sources" if len(details["sources"]) > 1 else "Source",
            "confidence_notes": f"{int(confidence * 100)}% confidence based on {details['count']}/{len(spec_results)} matching results"
        },
        "reasoning": " | ".join(details["reasoning"])
    }

async def search_specification(supplier: str, part_numbers: List[str], specifications: List[str]) -> Dict[str, Any]:
    try:
        log_stage("search_specification_start")
        all_results = []

        for part_number in part_numbers:
            log_stage(f"start_part:{part_number}")

            tasks = [
                asyncio.wait_for(get_specification_async(supplier, part_number, specifications), timeout=20)
                for _ in range(3)
            ]
            log_stage(f"launched_tasks:{part_number}")

            try:
                responses = await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as gather_error:
                logger.error(f"Gather failed for {part_number}: {gather_error}")
                continue

            log_stage(f"received_responses:{part_number}")
            responses = [r for r in responses if r is not None]

            if not responses:
                logger.warning(f"No valid responses received from Perplexity for part number {part_number}")
                log_stage(f"no_responses:{part_number}")
                continue

            processed_results = {}
            for response in responses:
                result = process_response(response, specifications)
                for spec, values in result.items():
                    if spec not in processed_results:
                        processed_results[spec] = []
                    processed_results[spec].extend(values)

            log_stage(f"starting_confidence:{part_number}")

            final_results = []
            for spec in specifications:
                spec_results = processed_results.get(spec, [])
                confidence_result = calculate_confidence(spec_results)
                final_results.append({
                    "name": spec,
                    **confidence_result
                })

            all_results.append({
                "part_number": part_number,
                "specifications": final_results
            })

        log_stage("search_specification_end")

        if not all_results:
            raise Exception("No valid results obtained for any part numbers")

        return {"results": all_results}

    except Exception as e:
        logger.error(f"Error in search_specification: {str(e)}")
        return {"error": str(e)}
