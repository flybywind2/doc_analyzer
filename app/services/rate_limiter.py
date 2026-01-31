"""
Rate Limiter Service
Provides rate limiting functionality for API calls
"""
import time
from collections import deque
from datetime import datetime, timedelta


class RateLimiter:
    """
    Rate limiter for API calls using sliding window algorithm
    
    Usage:
        limiter = RateLimiter(max_calls=10, time_window=60)
        
        # Before each API call
        limiter.wait_if_needed()
        # Make API call here
    """
    
    def __init__(self, max_calls: int = 10, time_window: int = 60):
        """
        Initialize rate limiter
        
        Args:
            max_calls: Maximum number of calls allowed in time window (default: 10)
            time_window: Time window in seconds (default: 60)
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = deque()
    
    def wait_if_needed(self):
        """
        Wait if rate limit is exceeded
        
        This method uses a sliding window algorithm to track API calls.
        If the rate limit is reached, it automatically waits until the
        oldest call expires from the time window.
        """
        now = datetime.now()
        
        # Remove calls outside the time window
        while self.calls and self.calls[0] < now - timedelta(seconds=self.time_window):
            self.calls.popleft()
        
        # If at limit, wait until oldest call expires
        if len(self.calls) >= self.max_calls:
            sleep_time = (self.calls[0] + timedelta(seconds=self.time_window) - now).total_seconds()
            if sleep_time > 0:
                print(f"⏳ Rate limit reached ({self.max_calls} calls/{self.time_window}s). Waiting {sleep_time:.1f} seconds...")
                time.sleep(sleep_time + 0.1)  # Add 0.1s buffer
                # Clean up expired calls after waiting
                now = datetime.now()
                while self.calls and self.calls[0] < now - timedelta(seconds=self.time_window):
                    self.calls.popleft()
        
        # Record this call
        self.calls.append(datetime.now())
    
    def reset(self):
        """Reset the rate limiter, clearing all call history"""
        self.calls.clear()
    
    def get_remaining_calls(self) -> int:
        """
        Get the number of remaining calls available in current window
        
        Returns:
            Number of calls that can be made without waiting
        """
        now = datetime.now()
        
        # Remove expired calls
        while self.calls and self.calls[0] < now - timedelta(seconds=self.time_window):
            self.calls.popleft()
        
        return max(0, self.max_calls - len(self.calls))
    
    def get_wait_time(self) -> float:
        """
        Get the time to wait before next call is available
        
        Returns:
            Seconds to wait (0 if calls are available)
        """
        now = datetime.now()
        
        # Remove expired calls
        while self.calls and self.calls[0] < now - timedelta(seconds=self.time_window):
            self.calls.popleft()
        
        if len(self.calls) < self.max_calls:
            return 0.0
        
        # Calculate wait time until oldest call expires
        wait_time = (self.calls[0] + timedelta(seconds=self.time_window) - now).total_seconds()
        return max(0.0, wait_time)
