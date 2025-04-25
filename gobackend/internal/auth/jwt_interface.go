// Package auth provides authentication and authorization functionality for the HideMe API.
// It includes JWT token handling, API key management, password hashing utilities, and
// authentication middleware components.
package auth

import (
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
)

// JWTValidator defines the interface for JWT validation operations.
// This interface allows for flexible JWT implementation and easier testing
// by decoupling token validation from the concrete implementation.
type JWTValidator interface {
	// ValidateToken validates a JWT token and returns its claims if valid.
	// It checks the token signature, expiration, and that the token type matches the expected type.
	//
	// Parameters:
	//   - tokenString: The JWT token to validate
	//   - expectedType: The expected token type (e.g., "access" or "refresh")
	//
	// Returns:
	//   - A pointer to CustomClaims containing the token's payload if valid
	//   - An error describing why validation failed, or nil if successful
	ValidateToken(tokenString string, expectedType string) (*CustomClaims, error)

	// ParseTokenWithoutValidation parses a token without validating it to extract the JWT ID.
	// This is useful for token revocation when we need the ID even if the token has expired.
	//
	// Parameters:
	//   - tokenString: The JWT token to parse
	//
	// Returns:
	//   - The JWT ID (jti claim)
	//   - An error if parsing fails
	ParseTokenWithoutValidation(tokenString string) (string, error)

	// GetConfig returns the JWT settings configuration used by this validator.
	//
	// Returns:
	//   - A pointer to the JWTSettings configuration
	GetConfig() *config.JWTSettings
}
