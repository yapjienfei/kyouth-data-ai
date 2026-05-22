#!/usr/bin/env python3
"""
Test script to verify rate limiting works correctly.
Tests Gemini 2.5 Flash with 6 requests (exceeds 5 RPM limit)
"""

import time
from prompt_model import prompt_model, rate_limiter, GOOGLE_API_KEY

def test_rate_limit_rpm():
    """
    Test RPM (Requests Per Minute) rate limiting.
    Makes 6 requests to gemini-2.5-flash and checks if the 6th is blocked.
    """
    
    if not GOOGLE_API_KEY:
        print("❌ GOOGLE_API_KEY not set. Cannot test Gemini rate limits.")
        return
    
    print("=" * 80)
    print("🧪 TESTING RPM RATE LIMIT - Gemini 2.5 Flash")
    print("=" * 80)
    print("\n📋 Test Plan:")
    print("   • Model: gemini-2.5-flash")
    print("   • Rate Limit: 5 requests per minute (RPM)")
    print("   • Will make: 6 requests")
    print("   • Expected: First 5 succeed, 6th gets rate limited")
    print("\n" + "-" * 80)
    
    # Reset rate limiter usage for clean test
    rate_limiter.usage['gemini-2.5-flash'] = {
        'requests': [],
        'tokens': [],
        'daily_requests': []
    }
    
    test_prompt = "Say 'Hello' in exactly 3 words."
    results = []
    
    # Make 6 requests
    for i in range(1, 7):
        print(f"\n📤 Request {i}/6")
        print(f"   Prompt: {test_prompt}")
        
        # Check rate limit status before request
        can_proceed, status_msg = rate_limiter.can_make_request('gemini-2.5-flash', estimated_tokens=10)
        print(f"   Pre-check: {status_msg}")
        
        # Make the request
        start_time = time.time()
        response = prompt_model('gemini-2.5-flash', test_prompt)
        elapsed = time.time() - start_time
        
        # Check if rate limited
        is_rate_limited = "Rate Limit" in response
        
        # Store result
        result = {
            'request_num': i,
            'success': not is_rate_limited,
            'rate_limited': is_rate_limited,
            'time': elapsed,
            'response': response[:100] if len(response) > 100 else response
        }
        results.append(result)
        
        # Display result
        if is_rate_limited:
            print(f"   ❌ RESULT: RATE LIMITED - {response[:80]}")
        else:
            print(f"   ✅ RESULT: SUCCESS - {response[:80]}")
        print(f"   ⏱️  Time: {elapsed:.2f} seconds")
        
        # Show current usage stats
        stats = rate_limiter.get_usage_stats('gemini-2.5-flash')
        if stats:
            print(f"   📊 Current usage: {stats['rpm_used']}/{stats['rpm_limit']} RPM")
        
        # Small delay between requests
        if i < 6:
            time.sleep(0.5)
    
    # Print summary
    print("\n" + "=" * 80)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 80)
    print(f"{'Request':<10} {'Status':<15} {'Time':<12} {'Rate Limited?'}")
    print("-" * 80)
    
    rate_limited_count = 0
    for result in results:
        status = "✅ SUCCESS" if result['success'] else "❌ FAILED"
        rate_limited = "✅ YES" if result['rate_limited'] else "❌ NO"
        print(f"{result['request_num']:<10} {status:<15} {result['time']:.2f}s{'':<6} {rate_limited}")
        if result['rate_limited']:
            rate_limited_count += 1
    
    print("-" * 80)
    
    # Verify test passed
    if rate_limited_count == 1:
        print("\n✅ TEST PASSED: Rate limiting worked correctly!")
        print("   • First 5 requests succeeded")
        print("   • 6th request was rate limited as expected")
    elif rate_limited_count > 1:
        print("\n⚠️  TEST PARTIALLY PASSED: Multiple requests were rate limited")
        print(f"   • {rate_limited_count} requests were blocked")
    else:
        print("\n❌ TEST FAILED: Rate limiting did NOT activate")
        print("   • All 6 requests succeeded - rate limits not enforced")
    
    # Show final usage stats
    print("\n" + "-" * 80)
    print("📈 FINAL RATE LIMIT STATUS:")
    final_stats = rate_limiter.get_usage_stats('gemini-2.5-flash')
    if final_stats:
        print(f"   RPM Used: {final_stats['rpm_used']}/{final_stats['rpm_limit']}")
    
    print("=" * 80)


if __name__ == "__main__":
    # Run RPM test only
    test_rate_limit_rpm()
    
    print("\n💡 TIP: Wait 1 minute and run again to see RPM counter reset")
    print("   The counter will automatically reset to 0 after 60 seconds")