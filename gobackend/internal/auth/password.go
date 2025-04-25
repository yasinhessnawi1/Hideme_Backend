// Package auth provides authentication and authorization functionality for the HideMe API.
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

// PasswordConfig holds the parameters for the Argon2id password hashing algorithm.
// Argon2id is a modern, secure password hashing algorithm that provides protection
// against both side-channel attacks and GPU-based attacks.
type PasswordConfig struct {
	// Memory is the amount of memory used by the algorithm, in KiB.
	Memory uint32

	// Iterations is the number of iterations (passes) over the memory.
	Iterations uint32

	// Parallelism is the degree of parallelism (number of threads).
	Parallelism uint8

	// SaltLength is the length of the randomly generated salt in bytes.
	SaltLength uint32

	// KeyLength is the length of the generated hash in bytes.
	KeyLength uint32
}

// DefaultPasswordConfig returns the default configuration for password hashing.
// These settings balance security and performance for most use cases.
//
// Returns:
//   - A pointer to a PasswordConfig with secure default settings
func DefaultPasswordConfig() *PasswordConfig {
	return &PasswordConfig{
		Memory:      constants.DefaultPasswordHashMemory,
		Iterations:  constants.DefaultPasswordHashIterations,
		Parallelism: constants.DefaultPasswordHashParallelism,
		SaltLength:  constants.DefaultPasswordHashSaltLength,
		KeyLength:   constants.DefaultPasswordHashKeyLength,
	}
}

// ConfigFromAppConfig creates a password config from the application config.
// This allows customization of hashing parameters through the application's configuration.
//
// Parameters:
//   - cfg: The application configuration containing password hash settings
//
// Returns:
//   - A pointer to a PasswordConfig with settings from the application config
func ConfigFromAppConfig(cfg *config.AppConfig) *PasswordConfig {
	return &PasswordConfig{
		Memory:      cfg.PasswordHash.Memory,
		Iterations:  cfg.PasswordHash.Iterations,
		Parallelism: cfg.PasswordHash.Parallelism,
		SaltLength:  cfg.PasswordHash.SaltLength,
		KeyLength:   cfg.PasswordHash.KeyLength,
	}
}

// HashPassword generates a hash of the provided password using Argon2id.
// It uses a randomly generated salt for each password to prevent rainbow table attacks.
// The password and salt are never logged to ensure security and privacy.
//
// Parameters:
//   - password: The plain text password to hash
//   - cfg: Configuration parameters for the Argon2id algorithm
//
// Returns:
//   - encodedHash: Base64-encoded password hash
//   - encodedSalt: Base64-encoded salt used in hashing
//   - error: Any error that occurred during the hashing process
func HashPassword(password string, cfg *PasswordConfig) (string, string, error) {
	// Generate a cryptographically secure random salt
	salt := make([]byte, cfg.SaltLength)
	if _, err := rand.Read(salt); err != nil {
		// Log error without including sensitive data
		utils.LogError(err, map[string]interface{}{
			"operation": "generate_salt",
			"category":  gdprlog.SensitiveLog,
		})
		return "", "", fmt.Errorf("failed to generate salt: %w", err)
	}

	// Hash the password using Argon2id with the configured parameters
	hash := argon2.IDKey(
		[]byte(password),
		salt,
		cfg.Iterations,
		cfg.Memory,
		cfg.Parallelism,
		cfg.KeyLength,
	)

	// Encode the hash and salt as base64 for safe storage
	encodedHash := base64.StdEncoding.EncodeToString(hash)
	encodedSalt := base64.StdEncoding.EncodeToString(salt)

	// Log successful password hashing without including sensitive data
	if gdprLogger := utils.GetGDPRLogger(); gdprLogger != nil {
		gdprLogger.Info("Password hashed successfully", map[string]interface{}{
			"operation": "hash_password",
			"success":   true,
			// No sensitive data is logged
		})
	}

	return encodedHash, encodedSalt, nil
}

// VerifyPassword compares a password with a hash and salt using Argon2id.
// It uses constant-time comparison to prevent timing attacks.
// Neither the password nor hash values are logged to ensure security and privacy.
//
// Parameters:
//   - password: The plain text password to verify
//   - encodedHash: Base64-encoded hash from previous HashPassword call
//   - encodedSalt: Base64-encoded salt from previous HashPassword call
//   - cfg: Configuration parameters for the Argon2id algorithm
//
// Returns:
//   - bool: True if the password matches, false otherwise
//   - error: Any error that occurred during verification
func VerifyPassword(password, encodedHash, encodedSalt string, cfg *PasswordConfig) (bool, error) {
	// Decode the hash and salt from base64
	hash, err := base64.StdEncoding.DecodeString(encodedHash)
	if err != nil {
		// Log error without including sensitive data
		utils.LogError(err, map[string]interface{}{
			"operation": "decode_hash",
			"category":  gdprlog.SensitiveLog,
		})
		return false, fmt.Errorf("failed to decode hash: %w", err)
	}

	salt, err := base64.StdEncoding.DecodeString(encodedSalt)
	if err != nil {
		// Log error without including sensitive data
		utils.LogError(err, map[string]interface{}{
			"operation": "decode_salt",
			"category":  gdprlog.SensitiveLog,
		})
		return false, fmt.Errorf("failed to decode salt: %w", err)
	}

	// Calculate the hash of the provided password with the same parameters
	comparisonHash := argon2.IDKey(
		[]byte(password),
		salt,
		cfg.Iterations,
		cfg.Memory,
		cfg.Parallelism,
		cfg.KeyLength,
	)

	// Use constant-time comparison to prevent timing attacks
	// This ensures that the time taken to compare hashes doesn't leak information
	match := subtle.ConstantTimeCompare(hash, comparisonHash) == 1

	// Log verification attempt without including sensitive data
	if gdprLogger := utils.GetGDPRLogger(); gdprLogger != nil {
		gdprLogger.Info("Password verification performed", map[string]interface{}{
			"operation": "verify_password",
			"success":   match,
			// No sensitive data is logged
		})
	}

	return match, nil
}

// GenerateRandomBytes generates cryptographically secure random bytes.
// This function uses Go's crypto/rand package to ensure cryptographic security.
//
// Parameters:
//   - length: The number of random bytes to generate
//
// Returns:
//   - A slice of random bytes
//   - An error if randomness generation fails
func GenerateRandomBytes(length uint32) ([]byte, error) {
	b := make([]byte, length)
	_, err := rand.Read(b)
	if err != nil {
		// Log error without including sensitive data
		utils.LogError(err, map[string]interface{}{
			"operation": "generate_random_bytes",
			"length":    length,
		})
		return nil, fmt.Errorf("failed to generate random bytes: %w", err)
	}
	return b, nil
}

// GenerateRandomString generates a cryptographically secure random string.
// It uses base64 URL encoding to convert random bytes to a string.
//
// Parameters:
//   - length: The desired length of the random string
//
// Returns:
//   - A random string of the specified length
//   - An error if randomness generation fails
func GenerateRandomString(length uint32) (string, error) {
	b, err := GenerateRandomBytes(length)
	if err != nil {
		return "", err
	}
	return base64.URLEncoding.EncodeToString(b)[:length], nil
}
