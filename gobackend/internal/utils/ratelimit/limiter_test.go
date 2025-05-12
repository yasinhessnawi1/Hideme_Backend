package ratelimit

import (
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNewLimiter(t *testing.T) {
	t.Run("Limiter initialized with correct values", func(t *testing.T) {
		// Arrange
		rate := float64(10)
		burst := 5

		// Act
		limiter := NewLimiter(rate, burst)

		// Assert
		require.NotNil(t, limiter)
		assert.Equal(t, rate, limiter.rate)
		assert.Equal(t, float64(burst), limiter.capacity)
		assert.Equal(t, float64(burst), limiter.tokens)
		assert.NotZero(t, limiter.lastTime)
	})

	t.Run("Zero rate is allowed", func(t *testing.T) {
		// Arrange
		rate := float64(0)
		burst := 5

		// Act
		limiter := NewLimiter(rate, burst)

		// Assert
		require.NotNil(t, limiter)
		assert.Equal(t, rate, limiter.rate)
		assert.Equal(t, float64(burst), limiter.capacity)
	})

	t.Run("Zero burst is allowed", func(t *testing.T) {
		// Arrange
		rate := float64(10)
		burst := 0

		// Act
		limiter := NewLimiter(rate, burst)

		// Assert
		require.NotNil(t, limiter)
		assert.Equal(t, rate, limiter.rate)
		assert.Equal(t, float64(burst), limiter.capacity)
		assert.Equal(t, float64(burst), limiter.tokens)
	})

	t.Run("Negative values are allowed but may lead to unexpected behavior", func(t *testing.T) {
		// Arrange
		rate := float64(-10)
		burst := -5

		// Act
		limiter := NewLimiter(rate, burst)

		// Assert
		require.NotNil(t, limiter)
		assert.Equal(t, rate, limiter.rate)
		assert.Equal(t, float64(burst), limiter.capacity)
		assert.Equal(t, float64(burst), limiter.tokens)
	})
}

func TestLimiter_Allow(t *testing.T) {
	t.Run("Allow requests within rate limit", func(t *testing.T) {
		// Arrange
		limiter := NewLimiter(10, 5) // 10 requests per second, burst of 5

		// Act & Assert
		// Should be able to make 5 requests immediately (burst capacity)
		for i := 0; i < 5; i++ {
			assert.True(t, limiter.Allow(), "Expected request %d to be allowed", i+1)
		}

		// The 6th request should be denied (no tokens left)
		assert.False(t, limiter.Allow(), "Expected 6th request to be denied")
	})

	t.Run("Tokens refill over time", func(t *testing.T) {
		// Arrange
		limiter := NewLimiter(10, 1) // 10 requests per second, burst of 1

		// Act & Assert
		// Use the first token
		assert.True(t, limiter.Allow())

		// Next request should be denied (no tokens left)
		assert.False(t, limiter.Allow())

		// Wait for a token to be added (at rate of 10 per second, should get 1 token in 100ms)
		time.Sleep(100 * time.Millisecond)

		// Should be allowed again
		assert.True(t, limiter.Allow())
	})

	t.Run("Tokens are capped at capacity", func(t *testing.T) {
		// Arrange
		limiter := NewLimiter(10, 5) // 10 requests per second, burst of 5

		// Use all tokens
		for i := 0; i < 5; i++ {
			limiter.Allow()
		}

		// Wait long enough for more than 5 tokens to be added theoretically
		// At 10 tokens per second, waiting for 1 second should add 10 tokens
		time.Sleep(1 * time.Second)

		// Act
		// We should only be able to make 5 requests despite waiting for 10 tokens
		// because the capacity is 5
		success := 0
		for i := 0; i < 10; i++ {
			if limiter.Allow() {
				success++
			}
		}

		// Assert
		assert.Equal(t, 5, success, "Expected only 5 requests to be allowed due to capacity limit")
	})

	t.Run("Zero rate means no refills", func(t *testing.T) {
		// Arrange
		limiter := NewLimiter(0, 3) // 0 requests per second, burst of 3

		// Use all initial tokens
		for i := 0; i < 3; i++ {
			assert.True(t, limiter.Allow())
		}

		// Wait some time, but rate is 0 so no tokens should be added
		time.Sleep(500 * time.Millisecond)

		// Act & Assert
		assert.False(t, limiter.Allow(), "Expected request to be denied due to zero refill rate")
	})

	t.Run("Zero capacity means no requests allowed", func(t *testing.T) {
		// Arrange
		limiter := NewLimiter(10, 0) // 10 requests per second, burst of 0

		// Act & Assert
		assert.False(t, limiter.Allow(), "Expected request to be denied due to zero capacity")

		// Even after waiting, no requests should be allowed
		time.Sleep(200 * time.Millisecond)
		assert.False(t, limiter.Allow(), "Expected request to be denied due to zero capacity even after waiting")
	})

	t.Run("Concurrent access is thread-safe", func(t *testing.T) {
		// Arrange
		limiter := NewLimiter(10, 50) // 10 requests per second, burst of 50

		var wg sync.WaitGroup
		numGoroutines := 10
		numRequestsPerGoroutine := 10
		wg.Add(numGoroutines)

		successCount := int32(0)

		// Act
		for i := 0; i < numGoroutines; i++ {
			go func() {
				defer wg.Done()
				for j := 0; j < numRequestsPerGoroutine; j++ {
					if limiter.Allow() {
						// Atomically increment success count
						//atomic.AddInt32(&successCount, 1)
						successCount++
					}
				}
			}()
		}

		wg.Wait()

		// Assert
		// Since we have a burst of 50 and 100 total requests, we expect exactly 50 to succeed
		assert.Equal(t, int32(50), successCount)
	})
}

func TestLimiter_ResetTokens(t *testing.T) {
	t.Run("Reset restores tokens to capacity", func(t *testing.T) {
		// Arrange
		limiter := NewLimiter(10, 5)

		// Use up all tokens
		for i := 0; i < 5; i++ {
			limiter.Allow()
		}

		// Verify tokens are depleted
		assert.False(t, limiter.Allow())

		// Act
		limiter.ResetTokens()

		// Assert
		// Should be able to make 5 requests again
		for i := 0; i < 5; i++ {
			assert.True(t, limiter.Allow(), "Expected request %d to be allowed after reset", i+1)
		}
	})

	t.Run("Reset updates lastTime", func(t *testing.T) {
		// Arrange
		limiter := NewLimiter(10, 5)
		originalTime := limiter.lastTime

		// Wait a bit to ensure time changes
		time.Sleep(100 * time.Millisecond)

		// Act
		limiter.ResetTokens()

		// Assert
		assert.True(t, limiter.lastTime.After(originalTime), "Expected lastTime to be updated")
	})

	t.Run("Reset with zero capacity", func(t *testing.T) {
		// Arrange
		limiter := NewLimiter(10, 0)

		// Act
		limiter.ResetTokens()

		// Assert
		assert.False(t, limiter.Allow(), "Expected request to be denied after reset with zero capacity")
	})

	t.Run("Reset can be called multiple times", func(t *testing.T) {
		// Arrange
		limiter := NewLimiter(10, 5)

		// Act
		for i := 0; i < 3; i++ {
			limiter.ResetTokens()
		}

		// Assert
		// Should still have full capacity
		for i := 0; i < 5; i++ {
			assert.True(t, limiter.Allow(), "Expected request %d to be allowed after multiple resets", i+1)
		}
	})
}
