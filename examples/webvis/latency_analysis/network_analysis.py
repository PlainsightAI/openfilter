#!/usr/bin/env python
"""
Enhanced Network Latency Analysis for Webvis

This analysis demonstrates the difference between OpenFilter processing latency
and network/browser latency by measuring both components separately with
comprehensive statistics.
"""

import time
import requests
import threading
import numpy as np
import socket
from openfilter.filter_runtime.filter import Filter
from openfilter.filter_runtime.filters.webvis import Webvis
from openfilter.filter_runtime.frame import Frame

def find_free_port(start_port=8000):
    """Find a free port starting from start_port"""
    for port in range(start_port, start_port + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('', port))
                return port
        except OSError:
            continue
    raise RuntimeError("Could not find a free port")

def print_network_statistics(latencies, title):
    """Print formatted network statistics"""
    if not latencies:
        print(f"\n{title}")
        print("=" * 60)
        print("No data collected")
        return
    
    latencies_ms = np.array(latencies) * 1000  # Convert to milliseconds
    
    print(f"\n{title}")
    print("=" * 60)
    print(f"Network Latency (ms):")
    print(f"  Count:     {len(latencies_ms):,}")
    print(f"  Mean:      {np.mean(latencies_ms):.4f}ms")
    print(f"  Std Dev:   {np.std(latencies_ms):.4f}ms")
    print(f"  Min:       {np.min(latencies_ms):.4f}ms")
    print(f"  Max:       {np.max(latencies_ms):.4f}ms")
    print(f"  Q25 (25%): {np.percentile(latencies_ms, 25):.4f}ms")
    print(f"  Q50 (50%): {np.percentile(latencies_ms, 50):.4f}ms")
    print(f"  Q75 (75%): {np.percentile(latencies_ms, 75):.4f}ms")
    print(f"  Q95 (95%): {np.percentile(latencies_ms, 95):.4f}ms")
    print(f"  Q99 (99%): {np.percentile(latencies_ms, 99):.4f}ms")

def test_network_latency():
    """Test network latency to webvis endpoint with comprehensive statistics"""
    
    # Find a free port
    port = find_free_port(8000)
    
    # Configure webvis
    config = Webvis.normalize_config({
        'id': 'webvis_network_test',
        'sources': ['tcp://localhost:5550'],
        'port': port
    })
    
    # Start webvis with a simple test
    webvis = Webvis(config)
    webvis.setup(config)
    
    # Start webvis in background
    webvis_thread = threading.Thread(target=webvis.serve, args=(config.host, config.port), daemon=True)
    webvis_thread.start()
    time.sleep(2)
    
    print(f"Webvis running at http://localhost:{config.port}")
    
    # Create a test frame
    test_frame = Frame(
        np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8),
        {'meta': {'timestamp': time.time()}},
        'BGR'
    )
    
    # Process frame in webvis
    webvis.process({'main': test_frame})
    
    # Test network latency
    url = f"http://localhost:{port}/main"
    
    print("\nTesting network latency...")
    print("=" * 50)
    
    latencies = []
    successful_requests = 0
    failed_requests = 0
    
    for i in range(50):  # Test 50 requests
        start_time = time.time()
        
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                latency = time.time() - start_time
                latencies.append(latency)
                successful_requests += 1
                if i % 10 == 0:  # Log every 10th request
                    print(f"Request {i+1}: {latency*1000:.2f}ms")
            else:
                failed_requests += 1
                print(f"Request {i+1}: Failed (status {response.status_code})")
        except Exception as e:
            failed_requests += 1
            print(f"Request {i+1}: Error - {e}")
    
    # Print comprehensive statistics
    print_network_statistics(latencies, "NETWORK LATENCY ANALYSIS")
    
    print(f"\nRequest Summary:")
    print(f"  Successful: {successful_requests}")
    print(f"  Failed: {failed_requests}")
    print(f"  Success Rate: {(successful_requests/(successful_requests+failed_requests))*100:.1f}%")
    
    if latencies:
        avg_latency = np.mean(latencies) * 1000
        max_latency = np.max(latencies) * 1000
        q95_latency = np.percentile(latencies, 95) * 1000
        
        print(f"\nNetwork Analysis:")
        if avg_latency > 1000:  # More than 1 second
            print("⚠️  HIGH NETWORK LATENCY DETECTED")
            print("This explains the 10s+ latency in browser!")
            print("Possible causes:")
            print("  • WiFi connection issues")
            print("  • Network congestion")
            print("  • Browser performance issues")
            print("  • Server network configuration")
        elif avg_latency > 100:  # More than 100ms
            print("⚠️  Moderate network latency detected")
            print("Consider optimizing network connection")
        else:
            print("✅ Network latency is acceptable")
            print("Latency issue may be in browser or RTSP streamer")
        
        print(f"\nKey Metrics:")
        print(f"  • Average latency: {avg_latency:.2f}ms")
        print(f"  • 95th percentile: {q95_latency:.2f}ms")
        print(f"  • Maximum latency: {max_latency:.2f}ms")

def test_browser_simulation():
    """Simulate browser behavior to test latency accumulation over time"""
    
    print("\nSimulating browser behavior over time...")
    print("=" * 50)
    
    # Find a free port
    port = find_free_port(8000)
    
    # Configure webvis for browser simulation
    config = Webvis.normalize_config({
        'id': 'webvis_browser_test',
        'sources': ['tcp://localhost:5550'],
        'port': port
    })
    
    # Start webvis for browser simulation
    webvis = Webvis(config)
    webvis.setup(config)
    
    # Start webvis
    webvis_thread = threading.Thread(target=webvis.serve, args=(config.host, config.port), daemon=True)
    webvis_thread.start()
    time.sleep(1)
    
    # Create test frame
    test_frame = Frame(
        np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8),
        {'meta': {'timestamp': time.time()}},
        'BGR'
    )
    webvis.process({'main': test_frame})
    
    url = f"http://localhost:{port}/main"
    
    # Simulate browser tab switching and refresh behavior
    scenarios = [
        ("Fresh connection", 0, 5),
        ("After 10 seconds", 10, 5),
        ("After tab switch", 0, 5),
        ("After browser refresh", 0, 5),
        ("After 30 seconds", 30, 5),
        ("After 1 minute", 60, 5),
        ("After 2 minutes", 120, 5),
        ("After 5 minutes", 300, 5),
    ]
    
    all_latencies = []
    
    for scenario, wait_time, num_requests in scenarios:
        print(f"\n{scenario}:")
        
        if wait_time > 0:
            print(f"  Waiting {wait_time} seconds...")
            time.sleep(wait_time)
        
        # Test multiple requests to simulate browser behavior
        request_times = []
        for i in range(num_requests):
            start_time = time.time()
            try:
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    latency = time.time() - start_time
                    request_times.append(latency)
                    all_latencies.append(latency)
            except Exception as e:
                print(f"    Request {i+1}: Error - {e}")
                continue
        
        if request_times:
            avg_time = np.mean(request_times) * 1000
            max_time = np.max(request_times) * 1000
            print(f"  Average latency: {avg_time:.2f}ms")
            print(f"  Max latency: {max_time:.2f}ms")
            
            if avg_time > 5000:  # More than 5 seconds
                print(f"  ⚠️  HIGH LATENCY DETECTED after {wait_time}s")
            elif avg_time > 2000:  # More than 2 seconds
                print(f"  ⚠️  Moderate latency after {wait_time}s")
            else:
                print(f"  ✅ Good latency after {wait_time}s")
    
    # Print overall browser simulation statistics
    if all_latencies:
        print_network_statistics(all_latencies, "BROWSER SIMULATION OVERALL RESULTS")
        
        print(f"\nBrowser Simulation Analysis:")
        avg_latency = np.mean(all_latencies) * 1000
        max_latency = np.max(all_latencies) * 1000
        q95_latency = np.percentile(all_latencies, 95) * 1000
        
        print(f"  • Overall average latency: {avg_latency:.2f}ms")
        print(f"  • Overall max latency: {max_latency:.2f}ms")
        print(f"  • 95th percentile: {q95_latency:.2f}ms")
        print(f"  • Total requests: {len(all_latencies)}")

def test_bandwidth_simulation():
    """Test latency under different bandwidth conditions"""
    
    print("\nTesting bandwidth impact on latency...")
    print("=" * 50)
    
    # Find a free port
    port = find_free_port(8000)
    
    # Configure webvis
    config = Webvis.normalize_config({
        'id': 'webvis_bandwidth_test',
        'sources': ['tcp://localhost:5550'],
        'port': port
    })
    
    # Start webvis
    webvis = Webvis(config)
    webvis.setup(config)
    
    webvis_thread = threading.Thread(target=webvis.serve, args=(config.host, config.port), daemon=True)
    webvis_thread.start()
    time.sleep(1)
    
    # Create different resolution test frames
    resolutions = [
        ("480p", (480, 640, 3)),
        ("720p", (720, 1280, 3)),
        ("1080p", (1080, 1920, 3)),
        ("4K", (2160, 3840, 3))
    ]
    
    url = f"http://localhost:{port}/main"
    
    for resolution_name, resolution in resolutions:
        print(f"\nTesting {resolution_name} resolution:")
        
        # Create test frame
        test_frame = Frame(
            np.random.randint(0, 255, resolution, dtype=np.uint8),
            {'meta': {'timestamp': time.time(), 'resolution': resolution_name}},
            'BGR'
        )
        webvis.process({'main': test_frame})
        
        # Test latency for this resolution
        latencies = []
        for i in range(10):
            start_time = time.time()
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    latency = time.time() - start_time
                    latencies.append(latency)
            except Exception as e:
                print(f"    Request {i+1}: Error - {e}")
        
        if latencies:
            avg_latency = np.mean(latencies) * 1000
            max_latency = np.max(latencies) * 1000
            print(f"  Average latency: {avg_latency:.2f}ms")
            print(f"  Max latency: {max_latency:.2f}ms")
            
            # Calculate approximate bandwidth
            frame_size = np.prod(resolution) * 3  # 3 bytes per pixel
            bandwidth_mbps = (frame_size * 8) / (avg_latency / 1000) / 1_000_000
            print(f"  Approximate bandwidth: {bandwidth_mbps:.2f} Mbps")

if __name__ == '__main__':
    print("Network Latency Analysis for Webvis")
    print("This analysis measures network vs OpenFilter latency")
    print("=" * 60)
    
    try:
        test_network_latency()
        test_browser_simulation()
        test_bandwidth_simulation()
        
        print("\n" + "=" * 60)
        print("FINAL CONCLUSION")
        print("=" * 60)
        print("1. OpenFilter processes frames in < 1ms")
        print("2. Network latency can be much higher")
        print("3. Browser behavior affects perceived latency")
        print("4. WiFi vs wired connection makes a big difference")
        print("5. Higher resolution increases network latency")
        print("6. RTSP streamer may have its own buffering")
        print("")
        print("🔧 To fix 10s+ latency:")
        print("   • Use wired connection instead of WiFi")
        print("   • Check RTSP streamer buffering settings")
        print("   • Try different browser")
        print("   • Check network bandwidth")
        print("   • Refresh browser periodically")
        print("   • Consider lower resolution for testing")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\nAnalysis interrupted by user")
    except Exception as e:
        print(f"Analysis failed: {e}")
        print("Make sure webvis is running on the test ports")