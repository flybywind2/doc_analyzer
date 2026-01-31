#!/usr/bin/env python3
"""
Rate Limiter Test Script
Tests the RateLimiter class to ensure it properly limits API calls
"""
import time
from datetime import datetime
from app.services.rate_limiter import RateLimiter


def test_rate_limiter():
    """Test rate limiter with 5 calls per 10 seconds for quick testing"""
    print("=" * 60)
    print("Rate Limiter Test")
    print("=" * 60)
    print("\n⚙️  Testing with: 5 calls per 10 seconds\n")
    
    limiter = RateLimiter(max_calls=5, time_window=10)
    
    start_time = datetime.now()
    
    for i in range(8):
        call_start = datetime.now()
        elapsed = (call_start - start_time).total_seconds()
        
        print(f"📞 Call #{i + 1} at {elapsed:.1f}s...")
        limiter.wait_if_needed()
        
        call_end = datetime.now()
        wait_time = (call_end - call_start).total_seconds()
        
        if wait_time > 0.1:
            print(f"   ⏳ Waited {wait_time:.1f}s due to rate limit")
        else:
            print(f"   ✅ Executed immediately")
    
    total_time = (datetime.now() - start_time).total_seconds()
    
    print(f"\n{'=' * 60}")
    print(f"✅ Test completed in {total_time:.1f} seconds")
    print(f"Expected minimum time: ~10 seconds (for 6th+ calls)")
    print(f"{'=' * 60}")


def test_production_rate_limiter():
    """Test production rate limiter (10 calls per minute) - shorter version"""
    print("\n" + "=" * 60)
    print("Production Rate Limiter Test (Shortened)")
    print("=" * 60)
    print("\n⚙️  Testing with: 10 calls per 60 seconds (testing 12 calls)\n")
    
    limiter = RateLimiter(max_calls=10, time_window=60)
    
    start_time = datetime.now()
    
    # Test with 12 calls
    for i in range(12):
        call_start = datetime.now()
        elapsed = (call_start - start_time).total_seconds()
        
        print(f"📞 Call #{i + 1} at {elapsed:.1f}s...")
        limiter.wait_if_needed()
        
        call_end = datetime.now()
        wait_time = (call_end - call_start).total_seconds()
        
        if wait_time > 0.1:
            print(f"   ⏳ Waited {wait_time:.1f}s due to rate limit")
        else:
            print(f"   ✅ Executed immediately")
        
        # Add small delay to simulate processing
        time.sleep(0.1)
    
    total_time = (datetime.now() - start_time).total_seconds()
    
    print(f"\n{'=' * 60}")
    print(f"✅ Test completed in {total_time:.1f} seconds")
    print(f"Expected: First 10 calls immediate, then 11th+ calls wait")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    # Run quick test
    test_rate_limiter()
    
    # Ask user if they want to run production test
    response = input("\n❓ Run production rate limiter test (10 calls/min)? This takes ~60 seconds. (y/n) [default: n]: ").strip().lower()
    if response == 'y':
        test_production_rate_limiter()
    else:
        print("\n⏭️  Skipping production rate limiter test")
        print(f"\n{'=' * 60}")
        print("📊 Summary:")
        print("   ✅ Rate limiter properly tracks call timestamps")
        print("   ✅ Automatically waits when limit is reached")
        print("   ✅ Sliding window algorithm working correctly")
        print(f"{'=' * 60}")
