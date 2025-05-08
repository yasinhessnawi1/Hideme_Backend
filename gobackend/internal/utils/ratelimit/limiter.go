// Package ratelimit provides rate limiting functionality for protecting API endpoints.
// It implements the token bucket algorithm with configurable rates and capacities.
package ratelimit

import (
	"sync"
	"time"
)

// Limiter represents a rate limiter for a specific client identity.
// It implements a token bucket algorithm where tokens are added at a
// fixed rate and requests consume tokens from the bucket.
type Limiter struct {
	// tokens is the current number of tokens in the bucket
	tokens float64

	// lastTime is the last time tokens were added to the bucket
	lastTime time.Time

	// rate is the token refill rate (tokens per second)
	rate float64

	// capacity is the maximum number of tokens the bucket can hold
	capacity float64

	// mu is a mutex to protect concurrent access to the bucket
	mu sync.Mutex
}

// Rate controls how many requests per second are allowed
type Rate struct {
	// RequestsPerSecond defines how many tokens are added per second
	RequestsPerSecond float64

	// Burst defines the maximum size of the token bucket
	Burst int
}

// NewLimiter creates a new rate limiter with the specified rate and burst capacity.
//
// Parameters:
//   - rate: The number of tokens per second to add to the bucket
//   - burst: The maximum capacity of the bucket
//
// Returns:
//   - A configured rate limiter
func NewLimiter(rate float64, burst int) *Limiter {
	return &Limiter{
		tokens:   float64(burst),
		lastTime: time.Now(),
		rate:     rate,
		capacity: float64(burst),
	}
}

// Allow checks if a request should be allowed based on the rate limit.
// It returns true if the request is allowed, false otherwise.
//
// Returns:
//   - true if the request is allowed
//   - false if the rate limit has been exceeded
func (l *Limiter) Allow() bool {
	l.mu.Lock()
	defer l.mu.Unlock()

	// Calculate how many tokens should have been added since the last request
	now := time.Now()
	elapsed := now.Sub(l.lastTime).Seconds()
	l.lastTime = now

	// Add tokens based on elapsed time
	l.tokens += elapsed * l.rate

	// Cap tokens at capacity
	if l.tokens > l.capacity {
		l.tokens = l.capacity
	}

	// Check if there's at least one token available
	if l.tokens < 1 {
		return false
	}

	// Consume a token
	l.tokens--
	return true
}

// ResetTokens resets the token count for the limiter.
// This is useful for administrative actions or testing.
func (l *Limiter) ResetTokens() {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.tokens = l.capacity
	l.lastTime = time.Now()
}
