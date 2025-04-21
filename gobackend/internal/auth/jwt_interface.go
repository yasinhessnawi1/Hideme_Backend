package auth

import (
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
)

// JWTValidator defines the interface for JWT validation
type JWTValidator interface {
	// ValidateToken validates a JWT token and returns its claims if valid
	ValidateToken(tokenString string, expectedType string) (*CustomClaims, error)

	// ParseTokenWithoutValidation parses a token without validating it to extract the JWT ID
	ParseTokenWithoutValidation(tokenString string) (string, error)

	// GetConfig returns the JWT settings configuration
	GetConfig() *config.JWTSettings
}
