"""
Testing script for the multithreaded file server.
Tests both race condition handling and rate limiting.

Usage:
    # Test race condition (unsafe mode)
    python test_server.py --test race --unsafe
    
    # Test race condition (safe mode with locks)
    python test_server.py --test race
    
    # Test rate limiting
    python test_server.py --test ratelimit
    
    # Run all tests
    python test_server.py --test all
"""

import requests
import threading
import time
import argparse
from collections import defaultdict
import sys

# Configuration
SERVER_URL = "http://localhost:5000"
TEST_FILE = "test.txt"  # Make sure this file exists in your public folder

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")

def print_success(text):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")

def print_fail(text):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")

def print_info(text):
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")

def print_warning(text):
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")

# ============================================================================
# TEST 1: Race Condition Testing
# ============================================================================

def test_race_condition(num_threads=20, num_requests=5):
    """
    Test race condition by sending concurrent requests to the same file.
    
    In UNSAFE mode: counters will be incorrect due to race conditions
    In SAFE mode: counters will be accurate
    """
    print_header("TEST 1: Race Condition Testing")
    
    print_info(f"Configuration:")
    print(f"  - Threads: {num_threads}")
    print(f"  - Requests per thread: {num_requests}")
    print(f"  - Total expected requests: {num_threads * num_requests}")
    print(f"  - Target: /{TEST_FILE}\n")
    
    # Record start counters
    print_info("Fetching initial counter value...")
    try:
        response = requests.get(f"{SERVER_URL}/", timeout=5)
        initial_html = response.text
        # Parse counter from HTML (this is approximate)
        print_success(f"Initial state captured\n")
    except Exception as e:
        print_fail(f"Could not connect to server: {e}")
        print_warning("Make sure the server is running!")
        return
    
    # Prepare for concurrent requests
    results = {"success": 0, "failed": 0}
    results_lock = threading.Lock()
    
    def make_requests(thread_id):
        """Each thread makes multiple requests"""
        for i in range(num_requests):
            try:
                response = requests.get(f"{SERVER_URL}/{TEST_FILE}", timeout=5)
                with results_lock:
                    if response.status_code == 200:
                        results["success"] += 1
                    else:
                        results["failed"] += 1
            except Exception as e:
                with results_lock:
                    results["failed"] += 1
                print(f"Thread {thread_id} request {i} failed: {e}")
    
    print_info("Launching concurrent requests...")
    start_time = time.time()
    
    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=make_requests, args=(i,))
        threads.append(t)
        t.start()
    
    # Wait for all threads
    for t in threads:
        t.join()
    
    elapsed = time.time() - start_time
    
    print_success(f"All threads completed in {elapsed:.2f} seconds\n")
    
    # Check results
    print_info("Results:")
    print(f"  - Successful requests: {results['success']}")
    print(f"  - Failed requests: {results['failed']}")
    print(f"  - Expected total: {num_threads * num_requests}\n")
    
    # Wait a bit for server to finish processing
    time.sleep(1)
    
    # Fetch the counter from the server
    print_info("Fetching final counter from server...")
    try:
        response = requests.get(f"{SERVER_URL}/", timeout=5)
        html = response.text
        
        # Parse counter for test.txt
        import re
        # Look for the counter in the HTML
        pattern = rf'{TEST_FILE}.*?requests:\s*(\d+)'
        match = re.search(pattern, html, re.DOTALL)
        
        if match:
            final_count = int(match.group(1))
            expected_count = num_threads * num_requests
            
            print(f"\n{Colors.BOLD}Counter Analysis:{Colors.ENDC}")
            print(f"  - Counter value: {final_count}")
            print(f"  - Expected value: {expected_count}")
            print(f"  - Difference: {expected_count - final_count}")
            
            if final_count == expected_count:
                print_success("\n✓ NO RACE CONDITION: Counter is accurate!")
                print_info("The locking mechanism is working correctly.")
            else:
                print_fail(f"\n✗ RACE CONDITION DETECTED: Lost {expected_count - final_count} increments!")
                print_warning("This is expected in --unsafe mode.")
                print_info("Run without --unsafe flag to see the fix.")
        else:
            print_warning(f"Could not find counter for {TEST_FILE} in HTML")
            
    except Exception as e:
        print_fail(f"Error fetching final counter: {e}")

# ============================================================================
# TEST 2: Rate Limiting
# ============================================================================

def test_rate_limiting(max_rate=5.0, test_duration=10):
    """
    Test rate limiting by simulating two clients:
    - Spammer: sends requests as fast as possible
    - Normal user: sends requests just below the rate limit
    """
    print_header("TEST 2: Rate Limiting")
    
    print_info(f"Configuration:")
    print(f"  - Server rate limit: {max_rate} req/s")
    print(f"  - Test duration: {test_duration} seconds")
    print(f"  - Spammer: unlimited rate")
    print(f"  - Normal user: {max_rate * 0.8:.1f} req/s\n")
    
    # Results tracking
    spammer_results = {"success": 0, "blocked": 0, "errors": 0}
    normal_results = {"success": 0, "blocked": 0, "errors": 0}
    
    spammer_lock = threading.Lock()
    normal_lock = threading.Lock()
    
    stop_flag = threading.Event()
    
    def spammer():
        """Sends requests as fast as possible"""
        while not stop_flag.is_set():
            try:
                response = requests.get(f"{SERVER_URL}/{TEST_FILE}", timeout=2)
                with spammer_lock:
                    if response.status_code == 200:
                        spammer_results["success"] += 1
                    elif response.status_code == 429:
                        spammer_results["blocked"] += 1
                    else:
                        spammer_results["errors"] += 1
            except Exception:
                with spammer_lock:
                    spammer_results["errors"] += 1
            # No delay - spam as fast as possible
    
    def normal_user():
        """Sends requests at a controlled rate (below limit)"""
        delay = 1.0 / (max_rate * 0.5)  # 80% of max rate
        while not stop_flag.is_set():
            try:
                response = requests.get(f"{SERVER_URL}/{TEST_FILE}", timeout=2)
                with normal_lock:
                    if response.status_code == 200:
                        normal_results["success"] += 1
                    elif response.status_code == 429:
                        normal_results["blocked"] += 1
                    else:
                        normal_results["errors"] += 1
            except Exception:
                with normal_lock:
                    normal_results["errors"] += 1
            time.sleep(delay)
    
    print_info("Starting rate limit test...")
    print_info(f"Spammer: sending requests at maximum speed")
    print_info(f"Normal user: sending at {max_rate * 0.5:.1f} req/s\n")
    
    # Start threads
    spammer_thread = threading.Thread(target=spammer, daemon=True)
    normal_thread = threading.Thread(target=normal_user, daemon=True)
    
    start_time = time.time()
    spammer_thread.start()
    normal_thread.start()
    
    # Progress indicator
    for i in range(test_duration):
        time.sleep(1)
        elapsed = i + 1
        print(f"  Progress: {elapsed}/{test_duration}s", end='\r')
    
    print()  # New line after progress
    
    # Stop threads
    stop_flag.set()
    time.sleep(0.5)  # Give threads time to finish
    
    elapsed = time.time() - start_time
    
    # Calculate statistics
    print_success(f"Test completed in {elapsed:.2f} seconds\n")
    
    print(f"{Colors.BOLD}SPAMMER Results:{Colors.ENDC}")
    total_spammer = spammer_results["success"] + spammer_results["blocked"]
    spammer_throughput = spammer_results["success"] / elapsed if elapsed > 0 else 0
    block_rate = (spammer_results["blocked"] / total_spammer * 100) if total_spammer > 0 else 0
    
    print(f"  - Successful requests: {spammer_results['success']}")
    print(f"  - Blocked (429): {spammer_results['blocked']} ({block_rate:.1f}%)")
    print(f"  - Errors: {spammer_results['errors']}")
    print(f"  - Throughput: {spammer_throughput:.2f} req/s")
    
    if spammer_throughput > max_rate * 1.5:
        print_fail("  ✗ Rate limiting may not be working correctly!")
    else:
        print_success(f"  ✓ Throughput limited to ~{max_rate} req/s")
    
    print(f"\n{Colors.BOLD}NORMAL USER Results:{Colors.ENDC}")
    normal_throughput = normal_results["success"] / elapsed if elapsed > 0 else 0
    
    print(f"  - Successful requests: {normal_results['success']}")
    print(f"  - Blocked (429): {normal_results['blocked']}")
    print(f"  - Errors: {normal_results['errors']}")
    print(f"  - Throughput: {normal_throughput:.2f} req/s")
    
    if normal_results["blocked"] > normal_results["success"] * 0.1:
        print_warning("  ⚠ Some requests blocked despite staying under limit")
    else:
        print_success("  ✓ Stayed under rate limit successfully")
    
    # Summary
    print(f"\n{Colors.BOLD}Summary:{Colors.ENDC}")
    print(f"  - Spammer blocked rate: {block_rate:.1f}%")
    print(f"  - Normal user blocked rate: {normal_results['blocked']/max(1, normal_results['success']+normal_results['blocked'])*100:.1f}%")
    
    if spammer_results["blocked"] > spammer_results["success"]:
        print_success("\n✓ RATE LIMITING WORKING: Spammer effectively throttled!")
    else:
        print_warning("\n⚠ Rate limiting may need adjustment")

# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Test the multithreaded file server")
    parser.add_argument("--test", choices=["race", "ratelimit", "all"], default="all",
                        help="Which test to run (default: all)")
    parser.add_argument("--server", default="http://localhost:5000",
                        help="Server URL (default: http://localhost:5000)")
    parser.add_argument("--threads", type=int, default=20,
                        help="Number of threads for race test (default: 20)")
    parser.add_argument("--duration", type=int, default=10,
                        help="Duration for rate limit test in seconds (default: 10)")
    
    args = parser.parse_args()
    
    global SERVER_URL
    SERVER_URL = args.server
    
    print_header("Multithreaded File Server Testing Suite")
    print_info(f"Server: {SERVER_URL}")
    print_info(f"Test file: {TEST_FILE}")
    
    # Check server connectivity
    print_info("\nChecking server connectivity...")
    try:
        response = requests.get(SERVER_URL, timeout=3)
        print_success("Server is reachable!\n")
    except Exception as e:
        print_fail(f"Cannot connect to server: {e}")
        print_warning("Please start the server first:")
        print("  python server.py --root public --port 5000")
        sys.exit(1)
    
    # Run tests
    if args.test in ["race", "all"]:
        test_race_condition(num_threads=args.threads, num_requests=5)
    
    if args.test in ["ratelimit", "all"]:
        if args.test == "all":
            time.sleep(2)  # Brief pause between tests
        test_rate_limiting(max_rate=10, test_duration=args.duration)
    
    print_header("Testing Complete!")

if __name__ == "__main__":
    main()