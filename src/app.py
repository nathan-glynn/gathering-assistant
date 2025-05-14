#Accept these updates
from flask.app import Flask
from flask import request, jsonify, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
import os
from dotenv import load_dotenv
from pathlib import Path
from src.search_utils import search_specification
from src.pdf_utils import process_pdf_for_specifications
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
logger.info(f"OPENAI_API_KEY present: {bool(os.getenv('OPENAI_API_KEY'))}")

# Initialize Flask app
app = Flask(__name__, template_folder='templates')

# Configure maximum content length for file uploads (50MB)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day", "10 per hour"]
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "port": os.getenv('PORT', 'not_set')})

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

@app.route('/process_pdf', methods=['POST'])
@limiter.limit("5 per minute")
async def process_pdf():
    try:
        start_time = time.time()
        
        logger.info("Received request to process PDF")
        
        # Check if PDF file is included
        if 'pdf_file' not in request.files:
            logger.error("No PDF file provided")
            return jsonify({"error": "No PDF file provided"}), 400
            
        pdf_file = request.files['pdf_file']
        if pdf_file.filename == '':
            logger.error("Empty filename")
            return jsonify({"error": "No PDF file selected"}), 400
            
        if not pdf_file.filename.endswith('.pdf'):
            logger.error(f"Invalid file type: {pdf_file.filename}")
            return jsonify({"error": "File must be a PDF"}), 400
        
        # Get other form data
        supplier = request.form.get('supplier', '')
        part_numbers = json.loads(request.form.get('part_numbers', '[]'))
        specifications = json.loads(request.form.get('specifications', '[]'))
        
        logger.info(f"Processing PDF for supplier: {supplier}, parts: {part_numbers}, specs: {specifications}")
        
        if not all([supplier, part_numbers, specifications]):
            missing_fields = []
            if not supplier: missing_fields.append("supplier")
            if not part_numbers: missing_fields.append("part_numbers")
            if not specifications: missing_fields.append("specifications")
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            logger.error(error_msg)
            return jsonify({"error": error_msg}), 400
        
        # Read the PDF file
        pdf_bytes = pdf_file.read()
        logger.info(f"PDF file size: {len(pdf_bytes)} bytes")
        
        # Process the PDF
        try:
            result = await process_pdf_for_specifications(pdf_bytes, supplier, part_numbers, specifications)
            logger.info("Successfully processed PDF and extracted specifications")
            return jsonify(result)
        except Exception as pdf_error:
            logger.error(f"Error in process_pdf_for_specifications: {str(pdf_error)}")
            raise
            
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error in process_pdf: {error_msg}")
        return jsonify({"error": error_msg}), 500

# if __name__ == '__main__':
#     port = int(os.getenv('PORT', 5001))
#     app.run(host='0.0.0.0', port=port, debug=os.getenv('FLASK_DEBUG', 'False').lower() == 'true') 