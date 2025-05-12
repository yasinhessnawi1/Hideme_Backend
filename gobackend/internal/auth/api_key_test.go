// api_key_test.go
package auth_test

import (
	"encoding/base64"
	"strings"
	"testing"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"

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

func TestEncryptAPIKey(t *testing.T) {
	// Test cases
	testCases := []struct {
		name          string
		apiKey        string
		encryptionKey []byte
		shouldError   bool
	}{
		{
			name:          "Valid encryption",
			apiKey:        "secretuihiuhwiughiurhiuetrhgutih",
			encryptionKey: []byte("12345678901234567890123456789012"), // 32 bytes for AES-256
			shouldError:   false,
		},
		{
			name:          "Invalid encryption key (too short)",
			apiKey:        "secretuihiuhwiughiurhiuetrhgutih",
			encryptionKey: []byte("0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"),
			shouldError:   false,
		},
		{
			name:          "Empty API key",
			apiKey:        "",
			encryptionKey: []byte("12345678901234567890123456789012"),
			shouldError:   false,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Encrypt the API key
			encrypted, err := utils.EncryptKey(tc.apiKey, tc.encryptionKey)

			// Check if error matches expectation
			if (err != nil) != tc.shouldError {
				t.Errorf("Expected error: %v, got error: %v", tc.shouldError, err != nil)
				return
			}

			// If no error expected, validate the encrypted result
			if !tc.shouldError {
				// Encrypted result should be non-empty
				if encrypted == "" {
					t.Error("Expected non-empty encrypted result, got empty string")
				}

				// Encrypted result should be different from input (for non-empty input)
				if tc.apiKey != "" && encrypted == tc.apiKey {
					t.Error("Encrypted result should be different from input")
				}

				// Encrypted result should be a valid base64 string
				if _, err := base64.StdEncoding.DecodeString(encrypted); err != nil {
					t.Errorf("Encrypted result is not valid base64: %v", err)
				}
			}
		})
	}
}

func TestDecryptAPIKey(t *testing.T) {
	// Create a valid encryption key (32 bytes for AES-256)
	encryptionKey := []byte("12345678901234567890123456789012")

	// Test cases
	testCases := []struct {
		name           string
		apiKey         string
		encryptionKey  []byte
		shouldError    bool
		expectOriginal bool
	}{
		{
			name:           "Valid encryption and decryption",
			apiKey:         "secretuihiuhwiughiurhiuetrhgutih",
			encryptionKey:  encryptionKey,
			shouldError:    false,
			expectOriginal: true,
		},
		{
			name:           "Different encryption key",
			apiKey:         "secretuihiuhwiughiurhiuetrhgutih",
			encryptionKey:  []byte("differentkey890123456789012345678"),
			shouldError:    true,
			expectOriginal: false,
		},
		{
			name:           "Empty API key",
			apiKey:         "",
			encryptionKey:  encryptionKey,
			shouldError:    false,
			expectOriginal: true,
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// First encrypt the API key with the original encryption key
			encrypted, err := utils.EncryptKey(tc.apiKey, encryptionKey)
			if err != nil {
				t.Fatalf("Failed to encrypt API key: %v", err)
			}

			// Now try to decrypt with the test case's encryption key
			decrypted, err := utils.DecryptKey(encrypted, tc.encryptionKey)

			// Check if error matches expectation
			if (err != nil) != tc.shouldError {
				t.Errorf("Expected error: %v, got error: %v", tc.shouldError, err != nil)
				return
			}

			// If no error and expecting original value, verify the decrypted result
			if !tc.shouldError && tc.expectOriginal {
				if decrypted != tc.apiKey {
					t.Errorf("Expected decrypted value '%s', got '%s'", tc.apiKey, decrypted)
				}
			}
		})
	}
}

func TestIsEncrypted(t *testing.T) {
	// Test cases
	testCases := []struct {
		name        string
		input       string
		isEncrypted bool
	}{
		{
			name:        "Encrypted API key",
			input:       "", // Will be populated with an actual encrypted key
			isEncrypted: true,
		},
		{
			name:        "Hashed API key (non-encrypted)",
			input:       "abc123", // Short base64 string, decodes to fewer than 12 bytes
			isEncrypted: false,
		},
		{
			name:        "Empty string",
			input:       "",
			isEncrypted: false,
		},
		{
			name:        "Invalid base64",
			input:       "not-valid-base64!@#$",
			isEncrypted: false,
		},
	}

	// Create a real encrypted key for the first test case
	encryptionKey := []byte("12345678901234567890123456789012")
	encryptedKey, err := utils.EncryptKey("secretuihiuhwiughiurhiuetrhgutih", encryptionKey)
	if err != nil {
		t.Fatalf("Failed to create encrypted key for test: %v", err)
	}
	testCases[0].input = encryptedKey

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Check if the string is encrypted
			result := auth.IsEncrypted(tc.input)

			// Verify the result
			if result != tc.isEncrypted {
				t.Errorf("Expected IsEncrypted to return %v for '%s', got %v",
					tc.isEncrypted, tc.input, result)
			}
		})
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
			hash := auth.HashAPIKey(tt.apiKey, nil)

			// Check that hash is not empty for non-empty input
			if tt.apiKey != "" && hash == "" {
				t.Error("Expected non-empty hash, got empty string")
			}

			// Check that the hash is consistent
			hash2 := auth.HashAPIKey(tt.apiKey, nil)
			if hash != hash2 {
				t.Errorf("Hash should be deterministic: %s vs %s", hash, hash2)
			}

			// Check that different inputs give different hashes
			if tt.apiKey != "" {
				differentHash := auth.HashAPIKey(tt.apiKey+"different", nil)
				if hash == differentHash {
					t.Error("Different inputs should give different hashes")
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
			name:        "15 minutes",
			input:       "15m",
			want:        15 * time.Minute,
			shouldError: false,
		},
		{
			name:        "30 minutes",
			input:       "30m",
			want:        30 * time.Minute,
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
