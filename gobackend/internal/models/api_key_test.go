package models_test

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestAPIKey_TableName(t *testing.T) {
	// Create a test API key
	apiKey := &models.APIKey{
		ID:         "key123",
		UserID:     100,
		APIKeyHash: "hashed_key",
		Name:       "Test Key",
		ExpiresAt:  time.Now().Add(24 * time.Hour),
		CreatedAt:  time.Now(),
	}

	// Verify the table name
	tableName := apiKey.TableName()
	assert.Equal(t, "api_keys", tableName, "TableName should return the correct database table name")
}

func TestNewAPIKey(t *testing.T) {
	// Test parameters
	userID := int64(100)
	name := "Test API Key"
	keyHash := "hashed_key_value"
	expiryDuration := 30 * 24 * time.Hour // 30 days

	// Create a new API key
	now := time.Now()
	apiKey := models.NewAPIKey(userID, name, keyHash, expiryDuration)

	// Verify the API key was created correctly
	assert.NotNil(t, apiKey, "NewAPIKey should return a non-nil APIKey")
	assert.Equal(t, userID, apiKey.UserID, "APIKey should have the provided user ID")
	assert.Equal(t, name, apiKey.Name, "APIKey should have the provided name")
	assert.Equal(t, keyHash, apiKey.APIKeyHash, "APIKey should have the provided key hash")
	assert.WithinDuration(t, now.Add(expiryDuration), apiKey.ExpiresAt, time.Second, "ExpiresAt should be set to now + expiry duration")
	assert.WithinDuration(t, now, apiKey.CreatedAt, time.Second, "CreatedAt should be set to current time")
	assert.Equal(t, "", apiKey.ID, "A new APIKey should have empty ID until explicitly set or saved to database")
}

func TestAPIKey_IsExpired(t *testing.T) {
	testCases := []struct {
		name            string
		expiresAt       time.Time
		shouldBeExpired bool
	}{
		{"Future expiry", time.Now().Add(time.Hour), false},
		{"Past expiry", time.Now().Add(-time.Hour), true},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Create an API key with the test expiry time
			apiKey := &models.APIKey{
				ID:         "key123",
				UserID:     100,
				APIKeyHash: "hashed_key",
				Name:       "Test Key",
				ExpiresAt:  tc.expiresAt,
				CreatedAt:  time.Now().Add(-24 * time.Hour), // Created a day ago
			}

			// Check if the API key is expired
			isExpired := apiKey.IsExpired()
			assert.Equal(t, tc.shouldBeExpired, isExpired, "IsExpired should correctly determine if the API key has expired")
		})
	}
}

func TestAPIKeyCreationRequest(t *testing.T) {
	// Create a test API key creation request
	request := &models.APIKeyCreationRequest{
		Name:     "My API Key",
		Duration: "30d",
	}

	// Verify the fields
	assert.Equal(t, "My API Key", request.Name)
	assert.Equal(t, "30d", request.Duration)
}

func TestAPIKeyResponse(t *testing.T) {
	// Create a test API key response
	now := time.Now()
	expiresAt := now.Add(30 * 24 * time.Hour)
	response := &models.APIKeyResponse{
		ID:        "key123",
		Name:      "My API Key",
		Key:       "actual_api_key_value",
		ExpiresAt: expiresAt,
		CreatedAt: now,
	}

	// Verify the fields
	assert.Equal(t, "key123", response.ID)
	assert.Equal(t, "My API Key", response.Name)
	assert.Equal(t, "actual_api_key_value", response.Key)
	assert.Equal(t, expiresAt, response.ExpiresAt)
	assert.Equal(t, now, response.CreatedAt)
}
