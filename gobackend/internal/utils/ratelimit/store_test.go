package ratelimit

import (
	"sync"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNewStore(t *testing.T) {
	t.Run("Store initialized with default rate", func(t *testing.T) {
		// Arrange
		defaultRate := Rate{RequestsPerSecond: 10, Burst: 20}
		cleanupInterval := 5 * time.Minute

		// Act
		store := NewStore(defaultRate, cleanupInterval)

		// Assert
		require.NotNil(t, store)
		assert.NotNil(t, store.limiters)
		assert.NotNil(t, store.rates)
		assert.Equal(t, defaultRate, store.rates["default"])
		assert.Equal(t, cleanupInterval, store.cleanupInterval)
	})

	t.Run("Store creates an empty map of limiters", func(t *testing.T) {
		// Arrange & Act
		store := NewStore(Rate{RequestsPerSecond: 10, Burst: 5}, time.Minute)

		// Assert
		assert.Empty(t, store.limiters)
	})
}

func TestStore_GetLimiter(t *testing.T) {
	t.Run("Creates new limiter for a client", func(t *testing.T) {
		// Arrange
		store := NewStore(Rate{RequestsPerSecond: 10, Burst: 5}, time.Minute)
		clientID := "192.168.1.1"

		// Act
		limiter := store.GetLimiter(clientID, "default")

		// Assert
		require.NotNil(t, limiter)
		assert.Equal(t, float64(10), limiter.rate)
		assert.Equal(t, float64(5), limiter.capacity)

		// Verify limiter was stored
		store.mu.RLock()
		storedLimiter, exists := store.limiters[clientID]
		store.mu.RUnlock()
		assert.True(t, exists)
		assert.Equal(t, limiter, storedLimiter)
	})

	t.Run("Returns existing limiter for known client", func(t *testing.T) {
		// Arrange
		store := NewStore(Rate{RequestsPerSecond: 10, Burst: 5}, time.Minute)
		clientID := "192.168.1.1"

		// First call to create the limiter
		firstLimiter := store.GetLimiter(clientID, "default")
		require.NotNil(t, firstLimiter)

		// Act - second call should return the same limiter
		secondLimiter := store.GetLimiter(clientID, "default")

		// Assert
		assert.Same(t, firstLimiter, secondLimiter)
	})

	t.Run("Uses category-specific rate when available", func(t *testing.T) {
		// Arrange
		store := NewStore(Rate{RequestsPerSecond: 10, Burst: 5}, time.Minute)
		apiRate := Rate{RequestsPerSecond: 5, Burst: 3}
		store.SetRate("api", apiRate)
		clientID := "192.168.1.1"

		// Act
		limiter := store.GetLimiter(clientID, "api")

		// Assert
		require.NotNil(t, limiter)
		assert.Equal(t, float64(5), limiter.rate)
		assert.Equal(t, float64(3), limiter.capacity)
	})

	t.Run("Falls back to default rate when category not found", func(t *testing.T) {
		// Arrange
		defaultRate := Rate{RequestsPerSecond: 10, Burst: 5}
		store := NewStore(defaultRate, time.Minute)
		clientID := "192.168.1.1"

		// Act
		limiter := store.GetLimiter(clientID, "non_existent_category")

		// Assert
		require.NotNil(t, limiter)
		assert.Equal(t, float64(10), limiter.rate)
		assert.Equal(t, float64(5), limiter.capacity)
	})

	t.Run("Concurrent access to GetLimiter is safe", func(t *testing.T) {
		// Arrange
		store := NewStore(Rate{RequestsPerSecond: 10, Burst: 5}, time.Minute)
		clientID := "192.168.1.1"
		numGoroutines := 10
		var wg sync.WaitGroup
		wg.Add(numGoroutines)

		// Act - Concurrently call GetLimiter
		for i := 0; i < numGoroutines; i++ {
			go func() {
				defer wg.Done()
				limiter := store.GetLimiter(clientID, "default")
				assert.NotNil(t, limiter)
			}()
		}

		// Wait for all goroutines to complete
		wg.Wait()

		// Assert - Should only have one limiter for the client ID
		store.mu.RLock()
		limitersCount := len(store.limiters)
		store.mu.RUnlock()
		assert.Equal(t, 1, limitersCount)
	})
}

func TestStore_SetRate(t *testing.T) {
	t.Run("Successfully sets new rate for category", func(t *testing.T) {
		// Arrange
		store := NewStore(Rate{RequestsPerSecond: 10, Burst: 5}, time.Minute)
		newRate := Rate{RequestsPerSecond: 20, Burst: 10}

		// Act
		store.SetRate("api", newRate)

		// Assert
		store.mu.RLock()
		rate, exists := store.rates["api"]
		store.mu.RUnlock()
		assert.True(t, exists)
		assert.Equal(t, newRate, rate)
	})

	t.Run("Successfully updates existing rate for category", func(t *testing.T) {
		// Arrange
		store := NewStore(Rate{RequestsPerSecond: 10, Burst: 5}, time.Minute)
		initialRate := Rate{RequestsPerSecond: 20, Burst: 10}
		updatedRate := Rate{RequestsPerSecond: 30, Burst: 15}

		// Set initial rate
		store.SetRate("api", initialRate)

		// Act
		store.SetRate("api", updatedRate)

		// Assert
		store.mu.RLock()
		rate, exists := store.rates["api"]
		store.mu.RUnlock()
		assert.True(t, exists)
		assert.Equal(t, updatedRate, rate)
	})

	t.Run("Can overwrite default rate", func(t *testing.T) {
		// Arrange
		initialDefaultRate := Rate{RequestsPerSecond: 10, Burst: 5}
		store := NewStore(initialDefaultRate, time.Minute)
		newDefaultRate := Rate{RequestsPerSecond: 20, Burst: 10}

		// Act
		store.SetRate("default", newDefaultRate)

		// Assert
		store.mu.RLock()
		rate := store.rates["default"]
		store.mu.RUnlock()
		assert.Equal(t, newDefaultRate, rate)
	})

	t.Run("Concurrent access to SetRate is safe", func(t *testing.T) {
		// Arrange
		store := NewStore(Rate{RequestsPerSecond: 10, Burst: 5}, time.Minute)
		numGoroutines := 10
		var wg sync.WaitGroup
		wg.Add(numGoroutines)

		// Act - Concurrently set different categories
		for i := 0; i < numGoroutines; i++ {
			go func(index int) {
				defer wg.Done()
				categoryName := "category_" + string(rune('A'+index))
				store.SetRate(categoryName, Rate{RequestsPerSecond: float64(index + 1), Burst: index + 1})
			}(i)
		}

		// Wait for all goroutines to complete
		wg.Wait()

		// Assert - Should have the expected number of categories
		store.mu.RLock()
		ratesCount := len(store.rates)
		store.mu.RUnlock()
		assert.Equal(t, numGoroutines+1, ratesCount) // +1 for default
	})
}

func TestStore_cleanup(t *testing.T) {
	t.Run("Cleanup removes limiters when too many exist", func(t *testing.T) {
		// Arrange
		store := NewStore(Rate{RequestsPerSecond: 10, Burst: 5}, time.Minute)

		// Add more than 10000 limiters to trigger cleanup
		for i := 0; i < 10001; i++ {
			clientID := "client_" + string(rune(i))
			store.limiters[clientID] = NewLimiter(10, 5)
		}
		assert.Greater(t, len(store.limiters), 10000)

		// Act
		store.cleanup()

		// Assert
		assert.Empty(t, store.limiters)
	})

	t.Run("Cleanup does nothing when few limiters exist", func(t *testing.T) {
		// Arrange
		store := NewStore(Rate{RequestsPerSecond: 10, Burst: 5}, time.Minute)

		// Add a few limiters, not enough to trigger cleanup
		for i := 0; i < 100; i++ {
			clientID := "client_" + string(rune(i))
			store.limiters[clientID] = NewLimiter(10, 5)
		}
		initialCount := len(store.limiters)
		assert.Equal(t, 100, initialCount)

		// Act
		store.cleanup()

		// Assert
		assert.Equal(t, initialCount, len(store.limiters))
	})
}

func TestStore_cleanupRoutine(t *testing.T) {
	t.Run("Cleanup routine executes periodically", func(t *testing.T) {
		// Use a very short cleanup interval for testing
		cleanupInterval := 100 * time.Millisecond
		store := NewStore(Rate{RequestsPerSecond: 10, Burst: 5}, cleanupInterval)

		// Add limiters exceeding the threshold
		for i := 0; i < 10001; i++ {
			clientID := "client_" + string(rune(i))
			store.limiters[clientID] = NewLimiter(10, 5)
		}

		// Wait for cleanup to run
		time.Sleep(cleanupInterval * 2) // Give enough time for cleanup to execute

		// Assert that cleanup occurred
		store.mu.RLock()
		count := len(store.limiters)
		store.mu.RUnlock()

		assert.Equal(t, 0, count, "Cleanup routine should have removed all limiters")
	})
}
