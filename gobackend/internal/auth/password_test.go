package auth_test

import (
	"testing"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
)

func TestDefaultPasswordConfig(t *testing.T) {
	cfg := auth.DefaultPasswordConfig()

	if cfg == nil {
		t.Error("Expected non-nil config")
		return
	}

	// Check default values
	if cfg.Memory != 64*1024 {
		t.Errorf("Expected Memory to be %d, got %d", 64*1024, cfg.Memory)
	}

	if cfg.Iterations != 3 {
		t.Errorf("Expected Iterations to be %d, got %d", 3, cfg.Iterations)
	}

	if cfg.Parallelism != 2 {
		t.Errorf("Expected Parallelism to be %d, got %d", 2, cfg.Parallelism)
	}

	if cfg.SaltLength != 16 {
		t.Errorf("Expected SaltLength to be %d, got %d", 16, cfg.SaltLength)
	}

	if cfg.KeyLength != 32 {
		t.Errorf("Expected KeyLength to be %d, got %d", 32, cfg.KeyLength)
	}
}

func TestHashPassword(t *testing.T) {
	// Use minimal config for faster tests
	cfg := &auth.PasswordConfig{
		Memory:      16 * 1024,
		Iterations:  1,
		Parallelism: 1,
		SaltLength:  16,
		KeyLength:   32,
	}

	// Test cases
	tests := []struct {
		name     string
		password string
	}{
		{
			name:     "Simple password",
			password: "password123",
		},
		{
			name:     "Complex password",
			password: "P@$$w0rd!123",
		},
		{
			name:     "Empty password",
			password: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Hash the password
			hash, salt, err := auth.HashPassword(tt.password, cfg)

			// Check for errors
			if err != nil {
				t.Errorf("HashPassword() error = %v", err)
				return
			}

			// Check that hash and salt are not empty
			if hash == "" {
				t.Error("Expected non-empty hash")
			}

			if salt == "" {
				t.Error("Expected non-empty salt")
			}

			// Try hashing again to check determinism with same salt
			// This is not a direct test but helps verify the function is working as expected
		})
	}
}

func TestVerifyPassword(t *testing.T) {
	// Use minimal config for faster tests
	cfg := &auth.PasswordConfig{
		Memory:      16 * 1024,
		Iterations:  1,
		Parallelism: 1,
		SaltLength:  16,
		KeyLength:   32,
	}

	// Test cases
	tests := []struct {
		name     string
		password string
	}{
		{
			name:     "Simple password",
			password: "password123",
		},
		{
			name:     "Complex password",
			password: "P@$$w0rd!123",
		},
		{
			name:     "Empty password",
			password: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Hash the password
			hash, salt, err := auth.HashPassword(tt.password, cfg)
			if err != nil {
				t.Fatalf("HashPassword() error = %v", err)
			}

			// Verify correct password
			match, err := auth.VerifyPassword(tt.password, hash, salt, cfg)

			// Check for errors
			if err != nil {
				t.Errorf("VerifyPassword() error = %v", err)
				return
			}

			// Check that it matches
			if !match {
				t.Error("Expected password to match")
			}

			// Verify incorrect password
			match, err = auth.VerifyPassword(tt.password+"wrong", hash, salt, cfg)

			// Check for errors
			if err != nil {
				t.Errorf("VerifyPassword() error = %v", err)
				return
			}

			// Check that it doesn't match
			if match {
				t.Error("Expected password not to match")
			}
		})
	}
}

func TestGenerateRandomBytes(t *testing.T) {
	// Test cases
	tests := []struct {
		name   string
		length uint32
	}{
		{
			name:   "Zero length",
			length: 0,
		},
		{
			name:   "16 bytes",
			length: 16,
		},
		{
			name:   "32 bytes",
			length: 32,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Generate random bytes
			bytes, err := auth.GenerateRandomBytes(tt.length)

			// Check for errors
			if err != nil {
				t.Errorf("GenerateRandomBytes() error = %v", err)
				return
			}

			// Check length
			if uint32(len(bytes)) != tt.length {
				t.Errorf("Expected length %d, got %d", tt.length, len(bytes))
			}

			// Check randomness (very basic check)
			if tt.length > 0 {
				// Generate another set of bytes
				bytes2, _ := auth.GenerateRandomBytes(tt.length)

				// They should be different (this is probabilistic but very likely)
				if bytes[0] == bytes2[0] && bytes[len(bytes)-1] == bytes2[len(bytes2)-1] {
					t.Error("Generated bytes should be random")
				}
			}
		})
	}
}

func TestGenerateRandomString(t *testing.T) {
	// Test cases
	tests := []struct {
		name   string
		length uint32
	}{
		{
			name:   "Zero length",
			length: 0,
		},
		{
			name:   "16 characters",
			length: 16,
		},
		{
			name:   "32 characters",
			length: 32,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Generate random string
			str, err := auth.GenerateRandomString(tt.length)

			// Check for errors
			if err != nil {
				t.Errorf("GenerateRandomString() error = %v", err)
				return
			}

			// Check length
			if uint32(len(str)) != tt.length {
				t.Errorf("Expected length %d, got %d", tt.length, len(str))
			}

			// Check randomness (very basic check)
			if tt.length > 0 {
				// Generate another string
				str2, _ := auth.GenerateRandomString(tt.length)

				// They should be different
				if str == str2 {
					t.Error("Generated strings should be random")
				}
			}
		})
	}
}
