from flask import Flask, request, jsonify, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
import os
from dotenv import load_dotenv
from pathlib import Path
from search_utils import search_specification
import time
import json
import asyncio
from functools import partial

# Load environment variables
root_dir = Path(__file__).resolve().parent.parent
env_path = root_dir / '.env'
load_dotenv(dotenv_path=env_path)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log environment variables (without sensitive values)
logger.info(f"Loading .env file from: {env_path}")
logger.info(f"PERPLEXITY_API_KEY present: {bool(os.getenv('PERPLEXITY_API_KEY'))}")

# Initialize Flask app
app = Flask(__name__, template_folder='templates')

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day", "10 per hour"]
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_specs', methods=['POST'])
@limiter.limit("10 per minute")
async def get_specs():
    try:
        start_time = time.time()
        
        logger.info("Received request for specifications")
        try:
            data = request.get_json()
            logger.info(f"Request data: {json.dumps(data)}")
        except Exception as json_error:
            logger.error(f"Error parsing JSON: {str(json_error)}")
            return jsonify({"error": "Invalid JSON data"}), 400

        supplier = data.get('supplier', '')
        part_numbers = data.get('part_numbers', [])
        specifications = data.get('specifications', [])

        logger.info(f"Processing request for supplier: {supplier}, parts: {part_numbers}, specs: {specifications}")

        if not all([supplier, part_numbers, specifications]):
            missing_fields = []
            if not supplier: missing_fields.append("supplier")
            if not part_numbers: missing_fields.append("part_numbers")
            if not specifications: missing_fields.append("specifications")
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            logger.error(error_msg)
            return jsonify({"error": error_msg}), 400

        try:
            result = await search_specification(supplier, part_numbers, specifications)
            logger.info("Successfully retrieved specifications")
            return jsonify(result)
        except Exception as search_error:
            logger.error(f"Error in search_specification: {str(search_error)}")
            raise

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error in get_specs: {error_msg}")
        return jsonify({"error": error_msg}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True) 