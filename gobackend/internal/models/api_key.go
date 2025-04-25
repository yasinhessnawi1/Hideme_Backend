package models

import (
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// APIKey represents an API key for authenticating with the system.
// API keys are used by external services (like the Python backend) to verify user identity.
type APIKey struct {
	ID         string    `json:"id" db:"key_id"`
	UserID     int64     `json:"user_id" db:"user_id"`
	APIKeyHash string    `json:"-" db:"api_key_hash"`
	Name       string    `json:"name" db:"name"`
	ExpiresAt  time.Time `json:"expires_at" db:"expires_at"`
	CreatedAt  time.Time `json:"created_at" db:"created_at"`
}

// TableName returns the database table name for the APIKey model.
func (ak *APIKey) TableName() string {
	return constants.TableAPIKeys
}

// NewAPIKey creates a new APIKey with the given parameters.
func NewAPIKey(userID int64, name string, keyHash string, expiryDuration time.Duration) *APIKey {
	now := time.Now()
	return &APIKey{
		UserID:     userID,
		APIKeyHash: keyHash,
		Name:       name,
		ExpiresAt:  now.Add(expiryDuration),
		CreatedAt:  now,
	}
}

// IsExpired checks if the API key has expired.
func (ak *APIKey) IsExpired() bool {
	return time.Now().After(ak.ExpiresAt)
}

// APIKeyCreationRequest represents a request to create a new API key.
type APIKeyCreationRequest struct {
	Name     string `json:"name" validate:"required,min=1,max=100"`
	Duration string `json:"duration" validate:"required,oneof=30d 90d 180d 365d"` // Duration in days
}

// APIKeyResponse represents the response for API key creation.
// This includes the unhashed key that should be shown to the user only once.
type APIKeyResponse struct {
	ID        string    `json:"id"`
	Name      string    `json:"name"`
	Key       string    `json:"key"`
	ExpiresAt time.Time `json:"expires_at"`
	CreatedAt time.Time `json:"created_at"`
}
