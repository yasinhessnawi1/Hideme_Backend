package ratelimit

import (
	"github.com/rs/zerolog/log"
	"sync"
	"time"
)

// Store manages rate limiters for multiple clients.
// It provides methods to get and clean up limiters.
type Store struct {
	// limiters maps client identifiers to their rate limiters
	limiters map[string]*Limiter

	// rates defines different rate limits for different client types
	rates map[string]Rate

	// mu protects concurrent access to the limiters map
	mu sync.RWMutex

	// cleanup interval for removing expired limiters
	cleanupInterval time.Duration
}

// NewStore creates a new store for managing rate limiters.
//
// Parameters:
//   - defaultRate: The default rate limit for clients
//   - cleanupInterval: How often to run cleanup of expired limiters
//
// Returns:
//   - A configured limiter store
func NewStore(defaultRate Rate, cleanupInterval time.Duration) *Store {
	store := &Store{
		limiters:        make(map[string]*Limiter),
		rates:           make(map[string]Rate),
		cleanupInterval: cleanupInterval,
	}

	// Set default rate
	store.rates["default"] = defaultRate

	// Start cleanup routine
	go store.cleanupRoutine()

	return store
}

// GetLimiter returns a rate limiter for the specified client.
// If a limiter doesn't exist for the client, a new one is created.
//
// Parameters:
//   - clientID: The unique identifier for the client (e.g., IP address)
//   - category: Optional category for different rate limits (e.g., "api", "auth")
//
// Returns:
//   - A rate limiter for the client
func (s *Store) GetLimiter(clientID string, category string) *Limiter {
	s.mu.RLock()
	limiter, exists := s.limiters[clientID]
	s.mu.RUnlock()

	if exists {
		return limiter
	}

	// Get the appropriate rate for this category
	rate, exists := s.rates[category]
	if !exists {
		rate = s.rates["default"]
	}

	// Create a new limiter
	limiter = NewLimiter(rate.RequestsPerSecond, rate.Burst)

	// Store the limiter
	s.mu.Lock()
	s.limiters[clientID] = limiter
	s.mu.Unlock()

	return limiter
}

// SetRate sets a rate limit for a specific category.
//
// Parameters:
//   - category: The category name (e.g., "api", "auth")
//   - rate: The rate configuration to apply
func (s *Store) SetRate(category string, rate Rate) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.rates[category] = rate
}

// cleanupRoutine periodically removes old limiters to prevent memory leaks.
// This runs in a separate goroutine.
func (s *Store) cleanupRoutine() {
	ticker := time.NewTicker(s.cleanupInterval)
	defer ticker.Stop()

	for range ticker.C {
		s.cleanup()
	}
}

// cleanup removes limiters that have been inactive for too long.
// This helps prevent memory leaks from many one-time clients.
func (s *Store) cleanup() {
	s.mu.Lock()
	defer s.mu.Unlock()

	// In a more advanced implementation, you might add an
	// lastAccess field to Limiter and remove those that
	// haven't been accessed recently
	if len(s.limiters) > 10000 {
		// If we have too many limiters, recreate the map
		// This is a simple approach - a more sophisticated
		// one would use LRU eviction or similar
		log.Warn().Msg("Rate limiter store growing too large, resetting")
		s.limiters = make(map[string]*Limiter)
	}
}
