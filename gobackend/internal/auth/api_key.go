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
	"time"

	"github.com/google/uuid"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

type APIKeyService struct {
	config *config.APIKeySettings
}

func NewAPIKeyService(config *config.APIKeySettings) *APIKeyService {
	return &APIKeyService{
		config: config,
	}
}

func (s *APIKeyService) GenerateAPIKey(userID int64, name string, duration time.Duration) (*models.APIKey, string, error) {
	// Generate a UUID for internal reference only
	keyID := uuid.New().String()

	// Generate a cryptographically secure random string for the API key
	randomPart, err := GenerateRandomString(constants.APIKeyRandomStringLength)
	if err != nil {
		return nil, "", utils.NewInternalServerError(err)
	}

	// Use only the random part as the API key
	apiKey := randomPart

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

func EncryptAPIKey(apiKey string, encryptionKey []byte) (string, error) {
	block, err := aes.NewCipher(encryptionKey[:32])
	if err != nil {
		return "", fmt.Errorf("failed to create cipher: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", fmt.Errorf("failed to create GCM: %w", err)
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err = io.ReadFull(rand.Reader, nonce); err != nil {
		return "", fmt.Errorf("failed to create nonce: %w", err)
	}

	ciphertext := gcm.Seal(nonce, nonce, []byte(apiKey), nil)

	return base64.StdEncoding.EncodeToString(ciphertext), nil
}

func DecryptAPIKey(encryptedAPIKey string, encryptionKey []byte) (string, error) {
	ciphertext, err := base64.StdEncoding.DecodeString(encryptedAPIKey)
	if err != nil {
		return "", fmt.Errorf("failed to decode base64: %w", err)
	}

	block, err := aes.NewCipher(encryptionKey[:32])
	if err != nil {
		return "", fmt.Errorf("failed to create cipher: %w", err)
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", fmt.Errorf("failed to create GCM: %w", err)
	}

	nonceSize := gcm.NonceSize()
	if len(ciphertext) < nonceSize {
		return "", errors.New("ciphertext too short")
	}

	nonce, ciphertext := ciphertext[:nonceSize], ciphertext[nonceSize:]

	plaintext, err := gcm.Open(nil, nonce, ciphertext, nil)
	if err != nil {
		return "", fmt.Errorf("failed to decrypt: %w", err)
	}

	return string(plaintext), nil
}

func IsEncrypted(securedAPIKey string) bool {
	bytes, err := base64.StdEncoding.DecodeString(securedAPIKey)
	if err != nil {
		return false
	}

	return len(bytes) >= 12
}

func HashAPIKey(apiKey string, encryptionKey []byte) string {
	if encryptionKey != nil && len(encryptionKey) >= 32 {
		encrypted, err := EncryptAPIKey(apiKey, encryptionKey)
		if err == nil {
			return encrypted
		}
		log.Error().Err(err).Msg("Failed to encrypt API key, falling back to SHA-256 hash")
	}

	hash := sha256.Sum256([]byte(apiKey))
	return hex.EncodeToString(hash[:])
}

func ParseAPIKey(apiKey string) (string, string, error) {
	// For compatibility with existing code, we create a dummy UUID as keyID
	// and treat the entire apiKey as the secret
	keyID := uuid.New().String()
	return keyID, apiKey, nil
}

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
