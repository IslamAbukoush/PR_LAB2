"""
Simple speed comparison: Single-threaded vs Multithreaded server

Usage:
    # Test old single-threaded server (port 5000)
    python old_server.py --port 5000
    
    # In another terminal, test new multithreaded server (port 5001)
    python server.py --port 5001
    
    # Run this comparison
    python compare_speed.py
    
    # Or specify ports
    python compare_speed.py --old-port 5000 --new-port 5001
"""

import requests
import threading
import time
import argparse

class Colors:
    HEADER = '\033[95m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    CYAN = '\033[96m'

def test_server(url, num_requests=50, concurrent=True):
    """
    Test a server with multiple requests.
    
    Args:
        url: Server URL
        num_requests: Total number of requests to send
        concurrent: If True, send all at once; if False, send sequentially
    
    Returns:
        elapsed_time: Time taken in seconds
        success_count: Number of successful requests
    """
    results = {"success": 0, "failed": 0}
    lock = threading.Lock()
    
    def make_request():
        try:
            response = requests.get(url, timeout=10)
            with lock:
                if response.status_code == 200:
                    results["success"] += 1
                else:
                    results["failed"] += 1
        except Exception as e:
            with lock:
                results["failed"] += 1
    
    start_time = time.time()
    
    if concurrent:
        # Send all requests at once (multithreaded client)
        threads = []
        for _ in range(num_requests):
            t = threading.Thread(target=make_request)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
    else:
        # Send requests one by one (sequential)
        for _ in range(num_requests):
            make_request()
    
    elapsed = time.time() - start_time
    
    return elapsed, results["success"], results["failed"]

def print_bar(label, value, max_value, width=40):
    """Print a simple progress bar"""
    filled = int(width * value / max_value) if max_value > 0 else 0
    bar = "█" * filled + "░" * (width - filled)
    print(f"  {label}: {bar} {value:.2f}s")

def main():
    parser = argparse.ArgumentParser(description="Compare single-threaded vs multithreaded server speed")
    parser.add_argument("--old-port", type=int, default=5000, help="Old server port (default: 5000)")
    parser.add_argument("--new-port", type=int, default=5001, help="New server port (default: 5001)")
    parser.add_argument("--requests", type=int, default=50, help="Number of concurrent requests (default: 50)")
    parser.add_argument("--host", default="localhost", help="Server host (default: localhost)")
    
    args = parser.parse_args()
    
    old_url = f"http://{args.host}:{args.old_port}"
    new_url = f"http://{args.host}:{args.new_port}"
    
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}  Server Speed Comparison: Single-threaded vs Multithreaded{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")
    
    print(f"{Colors.CYAN}Configuration:{Colors.ENDC}")
    print(f"  Old Server (single-threaded): {old_url}")
    print(f"  New Server (multithreaded):   {new_url}")
    print(f"  Concurrent requests:          {args.requests}")
    print()
    
    # Check connectivity
    print(f"{Colors.CYAN}Checking server connectivity...{Colors.ENDC}")
    try:
        requests.get(old_url, timeout=2)
        print(f"  {Colors.OKGREEN}✓{Colors.ENDC} Old server is reachable")
    except:
        print(f"  {Colors.FAIL}✗ Old server NOT reachable at {old_url}{Colors.ENDC}")
        print(f"    Start it with: python old_server.py --port {args.old_port}")
        return
    
    try:
        requests.get(new_url, timeout=2)
        print(f"  {Colors.OKGREEN}✓{Colors.ENDC} New server is reachable")
    except:
        print(f"  {Colors.FAIL}✗ New server NOT reachable at {new_url}{Colors.ENDC}")
        print(f"    Start it with: python server.py --port {args.new_port}")
        return
    
    print()
    
    # Test old server
    print(f"{Colors.CYAN}Testing OLD server (single-threaded)...{Colors.ENDC}")
    old_time, old_success, old_failed = test_server(old_url, args.requests, concurrent=True)
    print(f"  {Colors.OKGREEN}✓{Colors.ENDC} Completed: {old_success} success, {old_failed} failed")
    print(f"  {Colors.BOLD}Time: {old_time:.2f} seconds{Colors.ENDC}")
    print()
    
    # Small delay between tests
    time.sleep(1)
    
    # Test new server
    print(f"{Colors.CYAN}Testing NEW server (multithreaded)...{Colors.ENDC}")
    new_time, new_success, new_failed = test_server(new_url, args.requests, concurrent=True)
    print(f"  {Colors.OKGREEN}✓{Colors.ENDC} Completed: {new_success} success, {new_failed} failed")
    print(f"  {Colors.BOLD}Time: {new_time:.2f} seconds{Colors.ENDC}")
    print()
    
    # Results
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}  RESULTS{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")
    
    max_time = max(old_time, new_time)
    print_bar("Old (single-threaded)", old_time, max_time)
    print_bar("New (multithreaded)  ", new_time, max_time)
    print()
    
    # Calculate speedup
    speedup = old_time / new_time if new_time > 0 else 0
    improvement = ((old_time - new_time) / old_time * 100) if old_time > 0 else 0
    
    print(f"{Colors.BOLD}Performance Metrics:{Colors.ENDC}")
    print(f"  Old server time:  {old_time:.2f}s")
    print(f"  New server time:  {new_time:.2f}s")
    print(f"  Time saved:       {old_time - new_time:.2f}s")
    print()
    
    if speedup > 1.5:
        print(f"  {Colors.OKGREEN}✓ Speedup: {speedup:.2f}x faster ({improvement:.1f}% improvement){Colors.ENDC}")
        print(f"  {Colors.OKGREEN}{Colors.BOLD}🚀 MULTITHREADING MAKES A BIG DIFFERENCE!{Colors.ENDC}")
    elif speedup > 1.1:
        print(f"  {Colors.OKGREEN}✓ Speedup: {speedup:.2f}x faster ({improvement:.1f}% improvement){Colors.ENDC}")
        print(f"  {Colors.OKGREEN}Multithreading provides noticeable improvement{Colors.ENDC}")
    elif speedup > 0.9:
        print(f"  {Colors.WARNING}≈ Similar performance: {speedup:.2f}x ({improvement:.1f}% difference){Colors.ENDC}")
        print(f"  {Colors.WARNING}Try increasing --requests or add --simulate to server{Colors.ENDC}")
    else:
        print(f"  {Colors.FAIL}⚠ Slower: {speedup:.2f}x{Colors.ENDC}")
        print(f"  {Colors.WARNING}Note: Multithreading overhead may affect simple requests{Colors.ENDC}")

if __name__ == "__main__":
    main()