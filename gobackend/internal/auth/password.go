package auth

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/base64"
	"fmt"

	"golang.org/x/crypto/argon2"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
)

// PasswordConfig holds the parameters for the Argon2id password hashing algorithm
type PasswordConfig struct {
	Memory      uint32
	Iterations  uint32
	Parallelism uint8
	SaltLength  uint32
	KeyLength   uint32
}

// DefaultPasswordConfig returns the default configuration for password hashing
func DefaultPasswordConfig() *PasswordConfig {
	return &PasswordConfig{
		Memory:      64 * 1024,
		Iterations:  3,
		Parallelism: 2,
		SaltLength:  16,
		KeyLength:   32,
	}
}

// ConfigFromAppConfig creates a password config from the application config
func ConfigFromAppConfig(cfg *config.AppConfig) *PasswordConfig {
	return &PasswordConfig{
		Memory:      cfg.PasswordHash.Memory,
		Iterations:  cfg.PasswordHash.Iterations,
		Parallelism: cfg.PasswordHash.Parallelism,
		SaltLength:  cfg.PasswordHash.SaltLength,
		KeyLength:   cfg.PasswordHash.KeyLength,
	}
}

// HashPassword generates a hash of the provided password using Argon2id
// Returns the encoded hash and the salt used for hashing
func HashPassword(password string, cfg *PasswordConfig) (string, string, error) {
	// Generate a random salt
	salt := make([]byte, cfg.SaltLength)
	if _, err := rand.Read(salt); err != nil {
		return "", "", fmt.Errorf("failed to generate salt: %w", err)
	}

	// Hash the password using Argon2id
	hash := argon2.IDKey(
		[]byte(password),
		salt,
		cfg.Iterations,
		cfg.Memory,
		cfg.Parallelism,
		cfg.KeyLength,
	)

	// Encode the hash and salt as base64
	encodedHash := base64.StdEncoding.EncodeToString(hash)
	encodedSalt := base64.StdEncoding.EncodeToString(salt)

	return encodedHash, encodedSalt, nil
}

// VerifyPassword compares a password with a hash and salt using Argon2id
func VerifyPassword(password, encodedHash, encodedSalt string, cfg *PasswordConfig) (bool, error) {
	// Decode the hash and salt from base64
	hash, err := base64.StdEncoding.DecodeString(encodedHash)
	if err != nil {
		return false, fmt.Errorf("failed to decode hash: %w", err)
	}

	salt, err := base64.StdEncoding.DecodeString(encodedSalt)
	if err != nil {
		return false, fmt.Errorf("failed to decode salt: %w", err)
	}

	// Calculate the hash of the provided password
	comparisonHash := argon2.IDKey(
		[]byte(password),
		salt,
		cfg.Iterations,
		cfg.Memory,
		cfg.Parallelism,
		cfg.KeyLength,
	)

	// Use constant-time comparison to avoid timing attacks
	match := subtle.ConstantTimeCompare(hash, comparisonHash) == 1
	return match, nil
}

// GenerateRandomBytes generates cryptographically secure random bytes
func GenerateRandomBytes(length uint32) ([]byte, error) {
	b := make([]byte, length)
	_, err := rand.Read(b)
	if err != nil {
		return nil, fmt.Errorf("failed to generate random bytes: %w", err)
	}
	return b, nil
}

// GenerateRandomString generates a random string of the specified length
func GenerateRandomString(length uint32) (string, error) {
	b, err := GenerateRandomBytes(length)
	if err != nil {
		return "", err
	}
	return base64.URLEncoding.EncodeToString(b)[:length], nil
}
