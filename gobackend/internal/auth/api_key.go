// Package auth provides authentication and authorization functionality for the HideMe API.
// This file implements API key management for secure authentication of external services
// and applications, including generation, encryption, decryption, and validation of API keys.
package auth

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"time"

	"github.com/google/uuid"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// APIKeyService handles the generation and management of API keys.
// It provides methods for creating, encrypting, and validating API keys
// with configurable settings for expiration and security.
type APIKeyService struct {
	// config contains configuration settings for API key generation and validation
	config *config.APIKeySettings
}

// NewAPIKeyService creates a new APIKeyService with the specified configuration.
//
// Parameters:
//   - config: Configuration settings for API key generation, including default expiry times
//     and encryption settings
//
// Returns:
//   - A properly initialized APIKeyService
func NewAPIKeyService(config *config.APIKeySettings) *APIKeyService {
	return &APIKeyService{
		config: config,
	}
}

// GenerateAPIKey creates a new API key for a user.
// It generates a secure random key (16 or 32 bytes), hashes or encrypts it for storage,
// and creates a database model with appropriate metadata.
//
// Parameters:
//   - userID: The ID of the user who will own this API key
//   - name: A human-readable name/description for the key
//   - duration: How long the key should remain valid
//
// Returns:
//   - apiKeyModel: A database model containing the key metadata (not the key itself)
//   - apiKey: The raw API key to be provided to the user (only returned once)
//   - error: Any error encountered during generation
func (s *APIKeyService) GenerateAPIKey(userID int64, name string, duration time.Duration) (*models.APIKey, string, error) {
	// Generate a UUID for internal reference only
	keyID := uuid.New().String()

	// Generate a cryptographically secure random key (32 bytes for AES-256, or 16 for AES-128)
	keyBytes, err := GenerateRandomBytes(32) // 32 bytes = 256 bits (recommended)
	if err != nil {
		return nil, "", utils.NewInternalServerError(err)
	}
	// Base64-url encode the key for safe transport/storage
	apiKey := base64.RawURLEncoding.EncodeToString(keyBytes)

	// Get the encryption key from config
	var encryptionKey []byte
	if s.config != nil && s.config.EncryptionKey != "" {
		encryptionKey = []byte(s.config.EncryptionKey)
	}

	// Secure the API key for storage using encryption or hashing
	securedKey := HashAPIKey(apiKey, encryptionKey)

	// Set the expiry time based on the requested duration or default
	var expiryDuration time.Duration
	if duration > 0 {
		expiryDuration = duration
	} else {
		expiryDuration = s.config.DefaultExpiry
	}

	// Create the API key model for database storage
	apiKeyModel := models.NewAPIKey(userID, name, securedKey, expiryDuration)
	apiKeyModel.ID = keyID

	return apiKeyModel, apiKey, nil
}

// IsEncrypted determines if a secured API key is encrypted or hashed.
// It checks if the string is valid base64 and long enough to be an encrypted key.
//
// Parameters:
//   - securedAPIKey: The secured API key string from storage
//
// Returns:
//   - true if the key appears to be encrypted, false if it's likely a hash
func IsEncrypted(securedAPIKey string) bool {
	bytes, err := base64.StdEncoding.DecodeString(securedAPIKey)
	if err != nil {
		return false
	}

	return len(bytes) >= 12
}

// HashAPIKey secures an API key for storage.
// It attempts to encrypt the key if an encryption key is provided,
// otherwise it falls back to SHA-256 hashing.
//
// Parameters:
//   - apiKey: The plaintext API key to secure
//   - encryptionKey: The key to use for encryption (if nil, hashing is used)
//
// Returns:
//   - The secured API key (either encrypted or hashed)
func HashAPIKey(apiKey string, encryptionKey []byte) string {
	if len(encryptionKey) >= 32 {
		encrypted, err := utils.EncryptKey(apiKey, encryptionKey)
		if err == nil {
			return encrypted
		}
		log.Error().Err(err).Msg("Failed to encrypt API key, falling back to SHA-256 hash")
	}

	hash := sha256.Sum256([]byte(apiKey))
	return hex.EncodeToString(hash[:])
}

// ParseAPIKey parses a raw API key string into its components.
// This implementation assigns a new UUID as the key ID.
//
// Parameters:
//   - apiKey: The raw API key to parse
//
// Returns:
//   - keyID: A unique identifier for the key
//   - key: The API key itself
//   - error: Any error encountered during parsing
func ParseAPIKey(apiKey string) (string, string, error) {
	keyID := uuid.New().String()
	return keyID, apiKey, nil
}

// ParseDuration converts a string duration format to a time.Duration.
// Supported formats: "15m", "30m", "30d", "90d", "180d", "365d"
//
// Parameters:
//   - duration: A string representing a duration
//
// Returns:
//   - The parsed duration
//   - A validation error if the format is invalid
func ParseDuration(duration string) (time.Duration, error) {
	switch duration {
	case constants.APIKeyDurationFormat15Minutes:
		return constants.APIKeyDuration15Minutes, nil
	case constants.APIKeyDurationFormat30Minutes:
		return constants.APIKeyDuration30Minutes, nil
	case constants.APIKeyDurationFormat30Days:
		return constants.APIKeyDuration30Days, nil
	case constants.APIKeyDurationFormat90Days:
		return constants.APIKeyDuration90Days, nil
	case constants.APIKeyDurationFormat180Days:
		return constants.APIKeyDuration180Days, nil
	case constants.APIKeyDurationFormat365Days:
		return constants.APIKeyDuration365Days, nil
	default:
		return 0, utils.NewValidationError("duration", "Invalid duration. Must be one of: 15m, 30m, 30d, 90d, 180d, 365d")
	}
}

// FormatExpiryTime formats an expiry time into a human-readable string.
// It automatically selects the appropriate unit (hours, days, or months)
// based on the time remaining.
//
// Parameters:
//   - expiryTime: The expiry time to format
//
// Returns:
//   - A human-readable string representing the time until expiry
func FormatExpiryTime(expiryTime time.Time) string {
	if time.Until(expiryTime) < 24*time.Hour {
		hours := int(time.Until(expiryTime).Hours())
		return utils.Plural(hours, "hour")
	}

	if time.Until(expiryTime) < 30*24*time.Hour {
		days := int(time.Until(expiryTime).Hours() / 24)
		return utils.Plural(days, "day")
	}

	months := int(time.Until(expiryTime).Hours() / 24 / 30)
	return utils.Plural(months, "month")
}
