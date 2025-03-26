import unittest
import tempfile
import os
import json
import time
from src.app import app, serp_cache, llm_cache, search_pdf_content, CACHE_DIR
from unittest.mock import patch, MagicMock
import psutil
import concurrent.futures
from datetime import datetime

class TestStatistics:
    def __init__(self):
        self.cache_performance = {
            'cold_time': 0,
            'warm_time': 0,
            'improvement': 0
        }
        self.memory_usage = {
            'initial': 0,
            'final': 0,
            'increase': 0,
            'timestamps': [],
            'values': []
        }
        self.concurrent_requests = {
            'total_time': 0,
            'num_requests': 0,
            'avg_time': 0,
            'success_rate': 0
        }
        self.error_handling = {
            'total_tests': 0,
            'successful_tests': 0,
            'success_rate': 0
        }
        self.cache_stats = {
            'hits': 0,
            'misses': 0,
            'errors': 0
        }
        self.search_process = {
            'specifications': [],  # List of specification search results
            'pdf_matches': 0,     # Number of specs found in PDFs
            'web_matches': 0,     # Number of specs found via web search
            'not_found': 0,       # Number of specs not found
            'avg_confidence': 0,   # Average confidence score
            'search_paths': []     # Detailed search process for each spec
        }
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def add_search_result(self, specification: str, result: dict):
        """Track the search process for a specification"""
        search_path = {
            'specification': specification,
            'found_in_pdf': False,
            'found_in_web': False,
            'confidence': 0,
            'value': 'NOT_FOUND',
            'source': None,
            'time_taken': 0
        }

        if result.get('value') != 'NOT_FOUND' and result.get('value') != '-':
            if result.get('source', {}).get('url', '').endswith('.pdf'):
                search_path['found_in_pdf'] = True
                self.search_process['pdf_matches'] += 1
            else:
                search_path['found_in_web'] = True
                self.search_process['web_matches'] += 1
            
            search_path.update({
                'value': result['value'],
                'confidence': float(result.get('verification_status', 'low-confidence').split('-')[0].replace('high', '0.9').replace('medium', '0.6').replace('low', '0.3')),
                'source': result.get('source')
            })
        else:
            self.search_process['not_found'] += 1

        self.search_process['search_paths'].append(search_path)
        self.search_process['specifications'].append(specification)

        # Update average confidence
        confidences = [p['confidence'] for p in self.search_process['search_paths'] if p['confidence'] > 0]
        self.search_process['avg_confidence'] = sum(confidences) / len(confidences) if confidences else 0

    def to_dict(self):
        return {
            'timestamp': self.timestamp,
            'cache_performance': self.cache_performance,
            'memory_usage': self.memory_usage,
            'concurrent_requests': self.concurrent_requests,
            'error_handling': self.error_handling,
            'cache_stats': self.cache_stats,
            'search_process': self.search_process
        }

class TestSpecificationApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stats = TestStatistics()

    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        
        # Create cache directories
        os.makedirs(os.path.join(CACHE_DIR, 'serp'), exist_ok=True)
        os.makedirs(os.path.join(CACHE_DIR, 'llm'), exist_ok=True)
        
        # Clear caches before each test
        serp_cache.cleanup_expired()
        llm_cache.cleanup_expired()
        search_pdf_content.cache_clear()

    def test_cache_performance(self):
        """Test cache hit rates and response times"""
        print("\nTesting Cache Performance...")
        
        # Test data
        test_data = {
            'supplier': 'TestSupplier',
            'part_numbers': json.dumps(['PART123']),
            'specifications': json.dumps(['weight', 'dimensions'])
        }
        
        # First request (cold cache)
        start_time = time.time()
        response1 = self.client.post('/get_specs', data=test_data)
        cold_cache_time = time.time() - start_time
        
        # Second request (warm cache)
        start_time = time.time()
        response2 = self.client.post('/get_specs', data=test_data)
        warm_cache_time = time.time() - start_time
        
        # Update statistics
        self.stats.cache_performance.update({
            'cold_time': cold_cache_time,
            'warm_time': warm_cache_time,
            'improvement': ((cold_cache_time - warm_cache_time) / cold_cache_time * 100)
        })
        
        print(f"Cold cache response time: {cold_cache_time:.2f}s")
        print(f"Warm cache response time: {warm_cache_time:.2f}s")
        print(f"Cache performance improvement: {self.stats.cache_performance['improvement']:.1f}%")
        
        # Get cache statistics
        cache_stats = self.client.get('/cache_stats').json
        self.stats.cache_stats.update({
            'hits': cache_stats['serp_cache']['hits'] + cache_stats['llm_cache']['hits'],
            'misses': cache_stats['serp_cache']['misses'] + cache_stats['llm_cache']['misses'],
            'errors': cache_stats['serp_cache']['errors'] + cache_stats['llm_cache']['errors']
        })
        print("\nCache Statistics:")
        print(json.dumps(cache_stats, indent=2))

    def test_memory_usage(self):
        """Test memory usage under load"""
        print("\nTesting Memory Usage...")
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Generate load with multiple requests
        test_data = {
            'supplier': 'TestSupplier',
            'part_numbers': json.dumps(['PART123', 'PART456', 'PART789']),
            'specifications': json.dumps(['weight', 'dimensions', 'color'])
        }
        
        self.stats.memory_usage['timestamps'].append(0)
        self.stats.memory_usage['values'].append(initial_memory)
        
        for i in range(5):
            self.client.post('/get_specs', data=test_data)
            current_memory = process.memory_info().rss / 1024 / 1024
            self.stats.memory_usage['timestamps'].append((i + 1) * 2)  # 2-second intervals
            self.stats.memory_usage['values'].append(current_memory)
        
        final_memory = process.memory_info().rss / 1024 / 1024
        self.stats.memory_usage.update({
            'initial': initial_memory,
            'final': final_memory,
            'increase': final_memory - initial_memory
        })
        
        print(f"Initial memory usage: {initial_memory:.2f} MB")
        print(f"Final memory usage: {final_memory:.2f} MB")
        print(f"Memory increase: {self.stats.memory_usage['increase']:.2f} MB")

    def test_concurrent_requests(self):
        """Test handling of concurrent requests"""
        print("\nTesting Concurrent Requests...")
        
        test_data = {
            'supplier': 'TestSupplier',
            'part_numbers': json.dumps(['PART123']),
            'specifications': json.dumps(['weight'])
        }
        
        def make_request():
            return self.client.post('/get_specs', data=test_data)
        
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request) for _ in range(5)]
            responses = [f.result() for f in futures]
        
        total_time = time.time() - start_time
        success_count = sum(1 for r in responses if r.status_code == 200)
        
        self.stats.concurrent_requests.update({
            'total_time': total_time,
            'num_requests': len(responses),
            'avg_time': total_time / len(responses),
            'success_rate': (success_count / len(responses)) * 100
        })
        
        print(f"Concurrent requests completed in {total_time:.2f}s")
        print(f"Average request time: {self.stats.concurrent_requests['avg_time']:.2f}s")
        print(f"Success rate: {self.stats.concurrent_requests['success_rate']:.1f}%")

    @patch('src.app.GoogleSearch')
    @patch('src.app.OpenAI')
    def test_api_integration(self, mock_openai, mock_serp):
        """Test API integration with mocked responses"""
        print("\nTesting API Integration...")
        
        # Test data with multiple specifications
        test_data = {
            'supplier': 'TestSupplier',
            'part_numbers': json.dumps(['PART123']),
            'specifications': json.dumps(['weight', 'dimensions', 'color', 'material'])
        }
        
        # Mock SERP API responses for different specifications
        mock_serp_instance = MagicMock()
        mock_serp_instance.get_dict.return_value = {
            "organic_results": [
                {
                    "title": "Product Datasheet",
                    "link": "https://test.com/datasheet.pdf",
                    "snippet": "PART123 weight: 500g"
                },
                {
                    "title": "Supplier Website",
                    "link": "https://test.com/product",
                    "snippet": "Dimensions: 10x20x30 cm"
                }
            ]
        }
        mock_serp.return_value = mock_serp_instance
        
        # Mock OpenAI responses for different specifications
        responses = [
            # Weight - found in PDF
            '{"value": "500g", "verification_status": "high-confidence", "source": {"url": "test.com/datasheet.pdf", "title": "Product Datasheet", "confidence_notes": "Found in PDF"}}',
            # Dimensions - found on web
            '{"value": "10x20x30 cm", "verification_status": "medium-confidence", "source": {"url": "test.com/product", "title": "Supplier Website", "confidence_notes": "Found on supplier website"}}',
            # Color - not found
            '{"value": "NOT_FOUND", "verification_status": "not-found", "source": null}',
            # Material - low confidence
            '{"value": "aluminum", "verification_status": "low-confidence", "source": {"url": "test.com/forum", "title": "Forum Discussion", "confidence_notes": "Mentioned in user discussion"}}'
        ]
        
        mock_chat = MagicMock()
        mock_chat.completions.create.side_effect = [
            MagicMock(message=MagicMock(content=response))
            for response in responses
        ]
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat = mock_chat
        mock_openai.return_value = mock_openai_instance
        
        # Make the request
        start_time = time.time()
        response = self.client.post('/get_specs', data=test_data)
        total_time = time.time() - start_time
        
        # Track search results
        if response.status_code == 200:
            results = response.json.get('results', [])
            if results and 'specifications' in results[0]:
                for spec, result in zip(json.loads(test_data['specifications']), results[0]['specifications']):
                    result['time_taken'] = total_time / len(results[0]['specifications'])  # Approximate time per spec
                    self.stats.add_search_result(spec, result)
        
        print(f"API integration test status: {response.status_code}")
        print(f"Response data: {json.dumps(response.json, indent=2)}")
        print("\nSearch Process Statistics:")
        print(f"PDF Matches: {self.stats.search_process['pdf_matches']}")
        print(f"Web Matches: {self.stats.search_process['web_matches']}")
        print(f"Not Found: {self.stats.search_process['not_found']}")
        print(f"Average Confidence: {self.stats.search_process['avg_confidence']:.2%}")

    def test_error_handling(self):
        """Test error handling capabilities"""
        print("\nTesting Error Handling...")
        
        test_cases = [
            {
                'data': {
                    'supplier': 'TestSupplier',
                    'part_numbers': 'invalid_json',
                    'specifications': '[]'
                },
                'name': 'Invalid JSON'
            },
            {
                'data': {},
                'name': 'Missing Fields'
            }
        ]
        
        total_tests = len(test_cases)
        successful_tests = 0
        
        for test_case in test_cases:
            response = self.client.post('/get_specs', data=test_case['data'])
            if response.status_code in [400, 415]:  # Expected error codes
                successful_tests += 1
            print(f"{test_case['name']} handling: {response.status_code}")
        
        # Test file upload separately
        with tempfile.NamedTemporaryFile(suffix='.txt') as temp_file:
            temp_file.write(b'test content')
            temp_file.seek(0)
            data = {
                'supplier': 'TestSupplier',
                'part_numbers': json.dumps(['PART123']),
                'specifications': json.dumps(['weight']),
                'pdfs': (temp_file, 'test.txt')
            }
            response = self.client.post(
                '/get_specs',
                data=data,
                content_type='multipart/form-data'
            )
            if response.status_code in [400, 415]:
                successful_tests += 1
            print(f"Invalid file type handling: {response.status_code}")
            total_tests += 1
        
        self.stats.error_handling.update({
            'total_tests': total_tests,
            'successful_tests': successful_tests,
            'success_rate': (successful_tests / total_tests) * 100
        })
        
        print(f"Error handling success rate: {self.stats.error_handling['success_rate']:.1f}%")

    @classmethod
    def tearDownClass(cls):
        # Save test statistics
        stats_dir = os.path.join(os.path.dirname(__file__), 'test_stats')
        os.makedirs(stats_dir, exist_ok=True)
        
        stats_file = os.path.join(stats_dir, 'latest_stats.json')
        with open(stats_file, 'w') as f:
            json.dump(cls.stats.to_dict(), f, indent=2)

if __name__ == '__main__':
    unittest.main(verbosity=2) 