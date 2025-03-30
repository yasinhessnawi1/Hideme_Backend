package auth_test

import (
	"strings"
	"testing"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
)

func TestNewAPIKeyService(t *testing.T) {
	// Create config
	cfg := &config.APIKeySettings{
		DefaultExpiry: 24 * time.Hour,
	}

	// Create service
	service := auth.NewAPIKeyService(cfg)

	// Check if service is created
	if service == nil {
		t.Error("Expected service to be created, got nil")
	}
}

func TestGenerateAPIKey(t *testing.T) {
	// Create config
	cfg := &config.APIKeySettings{
		DefaultExpiry: 24 * time.Hour,
	}

	// Create service
	service := auth.NewAPIKeyService(cfg)

	// Test cases
	tests := []struct {
		name        string
		userID      int64
		keyName     string
		duration    time.Duration
		shouldError bool
	}{
		{
			name:        "Valid key with custom duration",
			userID:      123,
			keyName:     "Test Key",
			duration:    48 * time.Hour,
			shouldError: false,
		},
		{
			name:        "Valid key with default duration",
			userID:      456,
			keyName:     "Default Duration Key",
			duration:    0, // Use default
			shouldError: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Generate API key
			apiKey, rawKey, err := service.GenerateAPIKey(tt.userID, tt.keyName, tt.duration)

			// Check error
			if (err != nil) != tt.shouldError {
				t.Errorf("GenerateAPIKey() error = %v, shouldError %v", err, tt.shouldError)
				return
			}

			// If should not error, check results
			if !tt.shouldError {
				// Check API key model
				if apiKey == nil {
					t.Error("Expected API key model, got nil")
					return
				}

				// Check raw key
				if rawKey == "" {
					t.Error("Expected raw key, got empty string")
				}

				// Check user ID
				if apiKey.UserID != tt.userID {
					t.Errorf("Expected user ID %d, got %d", tt.userID, apiKey.UserID)
				}

				// Check name
				if apiKey.Name != tt.keyName {
					t.Errorf("Expected name %s, got %s", tt.keyName, apiKey.Name)
				}

				// Check ID exists
				if apiKey.ID == "" {
					t.Error("Expected ID to be set, got empty string")
				}

				// Check hash exists
				if apiKey.APIKeyHash == "" {
					t.Error("Expected hash to be set, got empty string")
				}

				// Check expiry time
				expectedDuration := tt.duration
				if expectedDuration == 0 {
					expectedDuration = cfg.DefaultExpiry
				}

				expectedExpiry := time.Now().Add(expectedDuration)
				tolerance := 5 * time.Second

				if apiKey.ExpiresAt.Before(expectedExpiry.Add(-tolerance)) ||
					apiKey.ExpiresAt.After(expectedExpiry.Add(tolerance)) {
					t.Errorf("Expiry time not within expected range: got %v, want ~%v",
						apiKey.ExpiresAt, expectedExpiry)
				}

				// Check raw key format
				parts := strings.Split(rawKey, ".")
				if len(parts) != 2 {
					t.Errorf("Expected raw key to be in format 'keyID.randomPart', got %s", rawKey)
				}

				// Check key ID matches
				if parts[0] != apiKey.ID {
					t.Errorf("Key ID in raw key doesn't match API key ID: %s vs %s", parts[0], apiKey.ID)
				}
			}
		})
	}
}

func TestHashAPIKey(t *testing.T) {
	// Test cases
	tests := []struct {
		name   string
		apiKey string
		want   string // We can't predict the exact hash, but we can check properties
	}{
		{
			name:   "Regular API key",
			apiKey: "abc123.xyz789",
		},
		{
			name:   "Empty API key",
			apiKey: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Hash the API key
			hash := auth.HashAPIKey(tt.apiKey)

			// Check that hash is not empty for non-empty input
			if tt.apiKey != "" && hash == "" {
				t.Error("Expected non-empty hash, got empty string")
			}

			// Check that the hash is consistent
			hash2 := auth.HashAPIKey(tt.apiKey)
			if hash != hash2 {
				t.Errorf("Hash should be deterministic: %s vs %s", hash, hash2)
			}

			// Check that different inputs give different hashes
			if tt.apiKey != "" {
				differentHash := auth.HashAPIKey(tt.apiKey + "different")
				if hash == differentHash {
					t.Error("Different inputs should give different hashes")
				}
			}
		})
	}
}

func TestParseAPIKey(t *testing.T) {
	// Test cases
	tests := []struct {
		name        string
		apiKey      string
		wantID      string
		wantSecret  string
		shouldError bool
	}{
		{
			name:        "Valid API key",
			apiKey:      "abc123.xyz789",
			wantID:      "abc123",
			wantSecret:  "xyz789",
			shouldError: false,
		},
		{
			name:        "Invalid format - no dot",
			apiKey:      "abc123xyz789",
			shouldError: true,
		},
		{
			name:        "Invalid format - too many dots",
			apiKey:      "abc.123.xyz",
			shouldError: true,
		},
		{
			name:        "Empty string",
			apiKey:      "",
			shouldError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Parse the API key
			id, secret, err := auth.ParseAPIKey(tt.apiKey)

			// Check error
			if (err != nil) != tt.shouldError {
				t.Errorf("ParseAPIKey() error = %v, shouldError %v", err, tt.shouldError)
				return
			}

			// If should not error, check results
			if !tt.shouldError {
				if id != tt.wantID {
					t.Errorf("ParseAPIKey() id = %v, want %v", id, tt.wantID)
				}

				if secret != tt.wantSecret {
					t.Errorf("ParseAPIKey() secret = %v, want %v", secret, tt.wantSecret)
				}
			}
		})
	}
}

func TestParseDuration(t *testing.T) {
	// Test cases
	tests := []struct {
		name        string
		input       string
		want        time.Duration
		shouldError bool
	}{
		{
			name:        "30 days",
			input:       "30d",
			want:        30 * 24 * time.Hour,
			shouldError: false,
		},
		{
			name:        "90 days",
			input:       "90d",
			want:        90 * 24 * time.Hour,
			shouldError: false,
		},
		{
			name:        "180 days",
			input:       "180d",
			want:        180 * 24 * time.Hour,
			shouldError: false,
		},
		{
			name:        "365 days",
			input:       "365d",
			want:        365 * 24 * time.Hour,
			shouldError: false,
		},
		{
			name:        "Invalid duration",
			input:       "10d",
			shouldError: true,
		},
		{
			name:        "Empty string",
			input:       "",
			shouldError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Parse the duration
			duration, err := auth.ParseDuration(tt.input)

			// Check error
			if (err != nil) != tt.shouldError {
				t.Errorf("ParseDuration() error = %v, shouldError %v", err, tt.shouldError)
				return
			}

			// If should not error, check result
			if !tt.shouldError && duration != tt.want {
				t.Errorf("ParseDuration() = %v, want %v", duration, tt.want)
			}
		})
	}
}

func TestFormatExpiryTime(t *testing.T) {
	now := time.Now()

	// Test cases
	tests := []struct {
		name       string
		expiryTime time.Time
		contains   string
	}{
		{
			name:       "Less than a day",
			expiryTime: now.Add(12 * time.Hour),
			contains:   "hours",
		},
		{
			name:       "Less than a month",
			expiryTime: now.Add(10 * 24 * time.Hour),
			contains:   "days",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Format the expiry time
			result := auth.FormatExpiryTime(tt.expiryTime)

			// Check that it contains the expected unit
			if !strings.Contains(result, tt.contains) {
				t.Errorf("FormatExpiryTime() = %v, should contain %v", result, tt.contains)
			}

			// Check that it's not empty
			if result == "" {
				t.Error("FormatExpiryTime() should not return empty string")
			}
		})
	}
}
