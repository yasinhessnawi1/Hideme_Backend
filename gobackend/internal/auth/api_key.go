// Package auth provides authentication and authorization functionality for the HideMe API.
// It includes JWT token handling, API key management, password hashing utilities, and
// authentication middleware components.
//
// This package follows security best practices for credential management, using
// strong cryptographic algorithms and proper error handling to maintain secure access control.
// All sensitive information handling includes considerations for GDPR compliance.
package auth

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// APIKeyService handles API key operations including generation, validation, and management.
// It provides secure API access through cryptographically secure key generation and validation.
type APIKeyService struct {
	config *config.APIKeySettings
}

// NewAPIKeyService creates a new APIKeyService with the specified configuration.
// It initializes the service with settings that control key generation and validation behavior.
//
// Parameters:
//   - config: Configuration settings for API keys including expiry times
//
// Returns:
//   - A properly initialized APIKeyService instance
func NewAPIKeyService(config *config.APIKeySettings) *APIKeyService {
	return &APIKeyService{
		config: config,
	}
}

// GenerateAPIKey creates a new API key for a user with specified parameters.
// The key consists of two parts: a UUID for the ID and a cryptographically secure
// random string for the secret part, combined with a dot separator.
//
// The API key is securely encrypted or hashed before storage to protect against exposure.
//
// Parameters:
//   - userID: The ID of the user who owns this API key
//   - name: A human-readable name for the key to help users identify keys
//   - duration: How long the key should be valid; if 0, uses the default expiry duration
//
// Returns:
//   - apiKeyModel: The database model (with secured key) for storing the API key
//   - apiKey: The plain text API key to be returned to the user (shown only once)
//   - error: Any error that occurred during key generation
func (s *APIKeyService) GenerateAPIKey(userID int64, name string, duration time.Duration) (*models.APIKey, string, error) {
	// Generate a UUID for the API key
	keyID := uuid.New().String()

	// Generate a cryptographically secure random string for the secret part
	randomPart, err := GenerateRandomString(constants.APIKeyRandomStringLength)
	if err != nil {
		return nil, "", utils.NewInternalServerError(err)
	}

	// Combine key ID and random part to form the API key
	// Using the format: keyID.randomPart
	apiKey := strings.Join([]string{keyID, randomPart}, ".")

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

// EncryptAPIKey encrypts an API key using AES-256-GCM.
// This allows the key to be decrypted by authorized services.
//
// Parameters:
//   - apiKey: The plain text API key to encrypt
//   - encryptionKey: The key used for encryption (must be at least 32 bytes)
//
// Returns:
//   - A base64-encoded encrypted string
//   - An error if encryption fails
func EncryptAPIKey(apiKey string, encryptionKey []byte) (string, error) {
	// Create a new cipher block
	block, err := aes.NewCipher(encryptionKey[:32]) // Use first 32 bytes as AES-256 key
	if err != nil {
		return "", fmt.Errorf("failed to create cipher: %w", err)
	}

	// Create a new GCM
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", fmt.Errorf("failed to create GCM: %w", err)
	}

	// Create a nonce
	nonce := make([]byte, gcm.NonceSize())
	if _, err = io.ReadFull(rand.Reader, nonce); err != nil {
		return "", fmt.Errorf("failed to create nonce: %w", err)
	}

	// Encrypt the data
	ciphertext := gcm.Seal(nonce, nonce, []byte(apiKey), nil)

	// Return the encrypted data as a base64 string
	return base64.StdEncoding.EncodeToString(ciphertext), nil
}

// DecryptAPIKey decrypts an API key using AES-256-GCM.
//
// Parameters:
//   - encryptedAPIKey: The base64-encoded encrypted API key
//   - encryptionKey: The key used for decryption (must be at least 32 bytes)
//
// Returns:
//   - The original plain text API key
//   - An error if decryption fails
func DecryptAPIKey(encryptedAPIKey string, encryptionKey []byte) (string, error) {
	// Decode the base64 string
	ciphertext, err := base64.StdEncoding.DecodeString(encryptedAPIKey)
	if err != nil {
		return "", fmt.Errorf("failed to decode base64: %w", err)
	}

	// Create a new cipher block
	block, err := aes.NewCipher(encryptionKey[:32]) // Use first 32 bytes as AES-256 key
	if err != nil {
		return "", fmt.Errorf("failed to create cipher: %w", err)
	}

	// Create a new GCM
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", fmt.Errorf("failed to create GCM: %w", err)
	}

	// Get the nonce size
	nonceSize := gcm.NonceSize()
	if len(ciphertext) < nonceSize {
		return "", errors.New("ciphertext too short")
	}

	// Extract the nonce
	nonce, ciphertext := ciphertext[:nonceSize], ciphertext[nonceSize:]

	// Decrypt the data
	plaintext, err := gcm.Open(nil, nonce, ciphertext, nil)
	if err != nil {
		return "", fmt.Errorf("failed to decrypt: %w", err)
	}

	return string(plaintext), nil
}

// IsEncrypted checks if an API key is encrypted with AES-256-GCM.
// This is used to determine whether to try decryption or fall back to hash comparison.
//
// Parameters:
//   - securedAPIKey: The secured API key to check
//
// Returns:
//   - true if the key appears to be encrypted, false otherwise
func IsEncrypted(securedAPIKey string) bool {
	// Try to decode as base64
	bytes, err := base64.StdEncoding.DecodeString(securedAPIKey)
	if err != nil {
		return false
	}

	// Check if it's long enough to contain a nonce (at least 12 bytes for GCM)
	return len(bytes) >= 12
}

// HashAPIKey secures an API key for storage.
// It uses AES-256-GCM encryption if a valid encryption key is provided,
// otherwise falls back to SHA-256 hashing.
//
// Parameters:
//   - apiKey: The plain text API key to secure
//   - encryptionKey: The key used for encryption (can be nil to force hashing)
//
// Returns:
//   - A secured representation of the API key (encrypted or hashed)
func HashAPIKey(apiKey string, encryptionKey []byte) string {
	if encryptionKey != nil && len(encryptionKey) >= 32 {
		// Try to encrypt the API key
		encrypted, err := EncryptAPIKey(apiKey, encryptionKey)
		if err == nil {
			return encrypted
		}
		// Log the error and fall back to hashing
		log.Error().Err(err).Msg("Failed to encrypt API key, falling back to SHA-256 hash")
	}

	// Fall back to SHA-256 hash
	hash := sha256.Sum256([]byte(apiKey))
	return hex.EncodeToString(hash[:])
}

// ParseAPIKey splits an API key into its ID and secret components.
// API keys have the format "id.secret" where id is a UUID and secret is a random string.
//
// Parameters:
//   - apiKey: The full API key to parse
//
// Returns:
//   - id: The ID part of the API key
//   - secret: The secret part of the API key
//   - error: An error if the API key format is invalid
func ParseAPIKey(apiKey string) (string, string, error) {
	parts := strings.Split(apiKey, ".")
	if len(parts) != 2 {
		return "", "", utils.NewInvalidTokenError()
	}

	return parts[0], parts[1], nil
}

// ParseDuration parses a user-friendly duration string into a time.Duration.
// This allows users to specify API key durations in a readable format.
//
// Parameters:
//   - duration: A string representing duration in format like "30d", "90d", etc.
//
// Returns:
//   - The parsed time.Duration
//   - An error if the duration format is invalid
func ParseDuration(duration string) (time.Duration, error) {
	switch duration {
	case constants.APIKeyDurationFormat30Days:
		return constants.APIKeyDuration30Days, nil
	case constants.APIKeyDurationFormat90Days:
		return constants.APIKeyDuration90Days, nil
	case constants.APIKeyDurationFormat180Days:
		return constants.APIKeyDuration180Days, nil
	case constants.APIKeyDurationFormat365Days:
		return constants.APIKeyDuration365Days, nil
	default:
		return 0, utils.NewValidationError("duration", "Invalid duration. Must be one of: 30d, 90d, 180d, 365d")
	}
}

// FormatExpiryTime formats the expiry time in a user-friendly way based on remaining time.
// It adapts the output format based on how much time remains before expiry.
//
// Parameters:
//   - expiryTime: The time when the API key expires
//
// Returns:
//   - A formatted string like "3 hours", "5 days", or "2 months"
func FormatExpiryTime(expiryTime time.Time) string {
	// If the expiry time is less than a day away
	if time.Until(expiryTime) < 24*time.Hour {
		hours := int(time.Until(expiryTime).Hours())
		return utils.Plural(hours, "hour")
	}

	// If the expiry time is less than a month away
	if time.Until(expiryTime) < 30*24*time.Hour {
		days := int(time.Until(expiryTime).Hours() / 24)
		return utils.Plural(days, "day")
	}

	// If the expiry time is more than a month away
	months := int(time.Until(expiryTime).Hours() / 24 / 30)
	return utils.Plural(months, "month")
}
