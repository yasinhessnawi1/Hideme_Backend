// Package models provides data structures and operations for the HideMe application.
// This file contains models related to API key management for secure authentication
// of external services and integrations.
package models

import (
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// APIKey represents an API key for authenticating with the system.
// API keys are used by external services (like the Python backend) to verify user identity.
// The system stores only the hash of the API key, not the original value, for security reasons.
type APIKey struct {
	// ID is the unique identifier for this API key
	ID string `json:"id" db:"key_id"`

	// UserID references the user who owns this API key
	UserID int64 `json:"user_id" db:"user_id"`

	// APIKeyHash stores a secure hash of the actual API key
	// The actual key is only displayed to the user once upon creation
	APIKeyHash string `json:"-" db:"api_key_hash"`

	// Name is a user-friendly identifier for this API key
	Name string `json:"name" db:"name"`

	// ExpiresAt defines when this API key will no longer be valid
	ExpiresAt time.Time `json:"expires_at" db:"expires_at"`

	// CreatedAt records when this API key was created
	CreatedAt time.Time `json:"created_at" db:"created_at"`
}

// TableName returns the database table name for the APIKey model.
// This method is used by ORM frameworks to determine where to persist this entity.
func (ak *APIKey) TableName() string {
	return constants.TableAPIKeys
}

// NewAPIKey creates a new APIKey with the given parameters.
//
// Parameters:
//   - userID: The ID of the user who owns this API key
//   - name: A user-friendly identifier for this API key
//   - keyHash: The secure hash of the actual API key value
//   - expiryDuration: How long this API key should remain valid
//
// Returns:
//   - A new APIKey pointer with all fields populated
//
// The actual API key value is never stored, only its hash.
// Both creation time and expiry time are managed automatically.
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
//
// Returns:
//   - true if the current time is after the expiry time, false otherwise
//
// This method helps maintain security by ensuring expired keys are not accepted.
func (ak *APIKey) IsExpired() bool {
	return time.Now().After(ak.ExpiresAt)
}

// APIKeyCreationRequest represents a request to create a new API key.
// This structure validates input parameters for API key creation.
type APIKeyCreationRequest struct {
	// Name is a user-friendly identifier for the API key
	// Must be between 1 and 100 characters
	Name string `json:"name" validate:"required,min=1,max=100"`

	// Duration specifies how long the API key should remain valid
	// Must be one of the predefined durations (30d, 90d, 180d, 365d)
	Duration string `json:"duration" validate:"required,oneof=30d 90d 180d 365d"` // Duration in days
}

// APIKeyResponse represents the response for API key creation.
// This includes the unhashed key that should be shown to the user only once.
// After initial display, the system will only store and use the key's hash.
type APIKeyResponse struct {
	// ID is the unique identifier for this API key
	ID string `json:"id"`

	// Name is the user-friendly identifier for this API key
	Name string `json:"name"`

	// Key is the actual API key value
	// This is only returned once at creation time and should be securely stored by the client
	Key string `json:"key"`

	// ExpiresAt defines when this API key will no longer be valid
	ExpiresAt time.Time `json:"expires_at"`

	// CreatedAt records when this API key was created
	CreatedAt time.Time `json:"created_at"`
}
