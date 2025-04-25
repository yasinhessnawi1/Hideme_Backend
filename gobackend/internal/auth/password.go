package auth

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/base64"
	"fmt"

	"golang.org/x/crypto/argon2"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils/gdprlog"
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
		Memory:      constants.DefaultPasswordHashMemory,
		Iterations:  constants.DefaultPasswordHashIterations,
		Parallelism: constants.DefaultPasswordHashParallelism,
		SaltLength:  constants.DefaultPasswordHashSaltLength,
		KeyLength:   constants.DefaultPasswordHashKeyLength,
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
		// Log error without sensitive data
		utils.LogError(err, map[string]interface{}{
			"operation": "generate_salt",
			"category":  gdprlog.SensitiveLog,
		})
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

	// Log successful password hashing without sensitive data
	if gdprLogger := utils.GetGDPRLogger(); gdprLogger != nil {
		gdprLogger.Info("Password hashed successfully", map[string]interface{}{
			"operation": "hash_password",
			"success":   true,
			// No sensitive data is logged
		})
	}

	return encodedHash, encodedSalt, nil
}

// VerifyPassword compares a password with a hash and salt using Argon2id
func VerifyPassword(password, encodedHash, encodedSalt string, cfg *PasswordConfig) (bool, error) {
	// Decode the hash and salt from base64
	hash, err := base64.StdEncoding.DecodeString(encodedHash)
	if err != nil {
		// Log error without sensitive data
		utils.LogError(err, map[string]interface{}{
			"operation": "decode_hash",
			"category":  gdprlog.SensitiveLog,
		})
		return false, fmt.Errorf("failed to decode hash: %w", err)
	}

	salt, err := base64.StdEncoding.DecodeString(encodedSalt)
	if err != nil {
		// Log error without sensitive data
		utils.LogError(err, map[string]interface{}{
			"operation": "decode_salt",
			"category":  gdprlog.SensitiveLog,
		})
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

	// Log verification attempt without sensitive data
	if gdprLogger := utils.GetGDPRLogger(); gdprLogger != nil {
		gdprLogger.Info("Password verification performed", map[string]interface{}{
			"operation": "verify_password",
			"success":   match,
			// No sensitive data is logged
		})
	}

	return match, nil
}

// GenerateRandomBytes generates cryptographically secure random bytes
func GenerateRandomBytes(length uint32) ([]byte, error) {
	b := make([]byte, length)
	_, err := rand.Read(b)
	if err != nil {
		// Log error without sensitive data
		utils.LogError(err, map[string]interface{}{
			"operation": "generate_random_bytes",
			"length":    length,
		})
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
