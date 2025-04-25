package auth

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"time"

	"github.com/google/uuid"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// APIKeyService handles API key operations
type APIKeyService struct {
	config *config.APIKeySettings
}

// NewAPIKeyService creates a new APIKeyService
func NewAPIKeyService(config *config.APIKeySettings) *APIKeyService {
	return &APIKeyService{
		config: config,
	}
}

// GenerateAPIKey creates a new API key
func (s *APIKeyService) GenerateAPIKey(userID int64, name string, duration time.Duration) (*models.APIKey, string, error) {
	// Generate a UUID for the API key
	keyID := uuid.New().String()

	// Generate a random string for the secret part
	randomPart, err := GenerateRandomString(constants.APIKeyRandomStringLength)
	if err != nil {
		return nil, "", utils.NewInternalServerError(err)
	}

	// Combine key ID and random part to form the API key
	apiKey := strings.Join([]string{keyID, randomPart}, ".")

	// Hash the API key for storage
	hashedKey := HashAPIKey(apiKey)

	// Set the expiry time based on the requested duration or default
	var expiryDuration time.Duration
	if duration > 0 {
		expiryDuration = duration
	} else {
		expiryDuration = s.config.DefaultExpiry
	}

	// Create the API key model
	apiKeyModel := models.NewAPIKey(userID, name, hashedKey, expiryDuration)
	apiKeyModel.ID = keyID

	return apiKeyModel, apiKey, nil
}

// HashAPIKey creates a SHA-256 hash of an API key
func HashAPIKey(apiKey string) string {
	hash := sha256.Sum256([]byte(apiKey))
	return hex.EncodeToString(hash[:])
}

// ParseAPIKey splits an API key into its ID and secret components
func ParseAPIKey(apiKey string) (string, string, error) {
	parts := strings.Split(apiKey, ".")
	if len(parts) != 2 {
		return "", "", utils.NewInvalidTokenError()
	}

	return parts[0], parts[1], nil
}

// ParseDuration parses a user-friendly duration string into a time.Duration
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

// FormatExpiryTime formats the expiry time in a user-friendly way
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
