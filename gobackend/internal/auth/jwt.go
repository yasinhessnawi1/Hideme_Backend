// Package auth provides authentication and authorization functionality for the HideMe API.
package auth

import (
	"errors"
	"fmt"
	"strconv"
	"time"

	"github.com/golang-jwt/jwt/v4"
	"github.com/google/uuid"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// JWT error definitions provide standardized errors for token-related failures.
var (
	// ErrInvalidToken is returned when a token's format, signature, or payload is invalid.
	ErrInvalidToken = errors.New(constants.ErrorInvalidToken)

	// ErrExpiredToken is returned when a token has expired.
	ErrExpiredToken = errors.New(constants.ErrorExpiredToken)

	// ErrInvalidSigningMethod is returned when a token uses an unexpected signing method.
	ErrInvalidSigningMethod = errors.New("invalid signing method")

	// ErrInvalidTokenClaims is returned when a token's claims cannot be parsed or are invalid.
	ErrInvalidTokenClaims = errors.New("invalid token claims")
)

// CustomClaims represents the claims in a JWT token, including both standard
// registered claims and application-specific claims.
type CustomClaims struct {
	// UserID is the unique identifier for the authenticated user.
	UserID int64 `json:"user_id"`

	// Username is the username of the authenticated user.
	Username string `json:"username"`

	// Email is the email address of the authenticated user.
	Email string `json:"email"`

	// TokenType indicates whether this is an "access" or "refresh" token.
	TokenType string `json:"token_type"`

	// RegisteredClaims includes standard JWT claims like expiration time.
	jwt.RegisteredClaims
}

// JWTService provides JWT token generation and validation functionality.
// It handles both access and refresh tokens with separate configurations.
type JWTService struct {
	// Config contains configuration settings for token generation and validation.
	Config *config.JWTSettings

	// config is for backward compatibility.
	config *config.JWTSettings
}

// NewJWTService creates a new JWTService instance with the provided configuration.
//
// Parameters:
//   - config: JWT settings including secret key, expiry times, and issuer
//
// Returns:
//   - A properly initialized JWTService
func NewJWTService(config *config.JWTSettings) *JWTService {
	return &JWTService{
		Config: config,
	}
}

// GetConfig returns the JWT settings configuration used by this service.
// If no configuration was provided, it returns default settings.
//
// Returns:
//   - A pointer to the JWTSettings configuration
func (s *JWTService) GetConfig() *config.JWTSettings {
	if s.Config == nil {
		return &config.JWTSettings{
			Expiry:        constants.DefaultJWTExpiry,
			RefreshExpiry: constants.DefaultJWTRefreshExpiry,
			Issuer:        constants.DefaultJWTIssuer,
		}
	}
	return s.Config
}

// GenerateAccessToken generates a new JWT access token for a user.
// Access tokens have shorter lifetimes and are used for API authentication.
//
// Parameters:
//   - userID: The unique identifier for the user
//   - username: The username of the user
//   - email: The email address of the user
//
// Returns:
//   - tokenString: The signed JWT token string
//   - jwtID: The unique identifier for this token (useful for token revocation)
//   - error: Any error that occurred during token generation
func (s *JWTService) GenerateAccessToken(userID int64, username, email string) (string, string, error) {
	return s.generateToken(userID, username, email, constants.TokenTypeAccess, s.Config.Expiry)
}

// GenerateRefreshToken generates a new JWT refresh token for a user.
// Refresh tokens have longer lifetimes and are used to obtain new access tokens.
//
// Parameters:
//   - userID: The unique identifier for the user
//   - username: The username of the user
//   - email: The email address of the user
//
// Returns:
//   - tokenString: The signed JWT token string
//   - jwtID: The unique identifier for this token (useful for token revocation)
//   - error: Any error that occurred during token generation
func (s *JWTService) GenerateRefreshToken(userID int64, username, email string) (string, string, error) {
	return s.generateToken(userID, username, email, constants.TokenTypeRefresh, s.Config.RefreshExpiry)
}

// generateToken creates a new JWT token with the provided parameters.
// This internal method is used by both GenerateAccessToken and GenerateRefreshToken.
//
// Parameters:
//   - userID: The unique identifier for the user
//   - username: The username of the user
//   - email: The email address of the user
//   - tokenType: The type of token ("access" or "refresh")
//   - expiry: How long the token should be valid
//
// Returns:
//   - tokenString: The signed JWT token string
//   - jwtID: The unique identifier for this token
//   - error: Any error that occurred during token generation
func (s *JWTService) generateToken(userID int64, username, email, tokenType string, expiry time.Duration) (string, string, error) {
	// Generate a unique token ID to enable token revocation
	jwtID := uuid.New().String()

	// Create claims with user information and expiry time
	now := time.Now()
	claims := CustomClaims{
		UserID:    userID,
		Username:  username,
		Email:     email,
		TokenType: tokenType,
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:    s.Config.Issuer,
			Subject:   fmt.Sprintf("%d", userID),
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(expiry)),
			NotBefore: jwt.NewNumericDate(now),
			ID:        jwtID,
		},
	}

	// Create the token with the claims and HMAC-SHA256 signing method
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)

	// Sign the token with the secret key
	tokenString, err := token.SignedString([]byte(s.Config.Secret))
	if err != nil {
		return "", "", fmt.Errorf("failed to sign token: %w", err)
	}

	return string(tokenString), jwtID, nil
}

// ValidateToken validates a JWT token and returns its claims if valid.
// It checks the token signature, expiration, and that the token type matches the expected type.
//
// Parameters:
//   - tokenString: The JWT token to validate
//   - expectedType: The expected token type ("access" or "refresh")
//
// Returns:
//   - A pointer to CustomClaims containing the token's payload if valid
//   - An error describing why validation failed, or nil if successful
func (s *JWTService) ValidateToken(tokenString string, expectedType string) (*CustomClaims, error) {
	// Parse the token with our custom claims type
	token, err := jwt.ParseWithClaims(tokenString, &CustomClaims{}, func(token *jwt.Token) (interface{}, error) {
		// Validate the signing method is HMAC-SHA256
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, ErrInvalidSigningMethod
		}
		return []byte(s.Config.Secret), nil
	})

	// Handle parsing errors with specific error types
	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return nil, utils.NewExpiredTokenError()
		}
		return nil, utils.NewInvalidTokenError()
	}

	// Check if the token is valid (correctly signed and not expired)
	if !token.Valid {
		return nil, utils.NewInvalidTokenError()
	}

	// Extract and validate the claims
	claims, ok := token.Claims.(*CustomClaims)
	if !ok {
		return nil, utils.NewInvalidTokenError()
	}

	// Validate the token type matches the expected type
	if claims.TokenType != expectedType {
		return nil, utils.NewInvalidTokenError()
	}

	return claims, nil
}

// ParseTokenWithoutValidation parses a token without validating it to extract the JWT ID.
// This is useful for token revocation when we need the ID even if the token has expired.
//
// Parameters:
//   - tokenString: The JWT token to parse
//
// Returns:
//   - The JWT ID (jti claim)
//   - An error if parsing fails
func (s *JWTService) ParseTokenWithoutValidation(tokenString string) (string, error) {
	// Parse the token without validating the signature
	token, _ := jwt.ParseWithClaims(tokenString, &CustomClaims{}, func(token *jwt.Token) (interface{}, error) {
		return []byte(""), nil // We don't actually validate the signature here
	})

	// Extract the claims
	if claims, ok := token.Claims.(*CustomClaims); ok {
		return claims.ID, nil
	}

	return "", ErrInvalidTokenClaims
}

// ExtractUserIDFromToken extracts the user ID from a token string.
// It validates the token first to ensure it's a valid access token.
//
// Parameters:
//   - tokenString: The JWT token to extract the user ID from
//
// Returns:
//   - The user ID if the token is valid
//   - An error if the token is invalid or expired
func (s *JWTService) ExtractUserIDFromToken(tokenString string) (int64, error) {
	claims, err := s.ValidateToken(tokenString, constants.TokenTypeAccess)
	if err != nil {
		return 0, err
	}
	return claims.UserID, nil
}

// RefreshTokens validates a refresh token and issues new access and refresh tokens.
// This implements the token refresh flow for maintaining user sessions.
//
// Parameters:
//   - refreshToken: The refresh token to validate
//   - userID: The expected user ID (for additional validation)
//   - username: The username to include in the new tokens
//   - email: The email to include in the new tokens
//
// Returns:
//   - accessToken: The new access token
//   - accessJWTID: The ID of the new access token
//   - newRefreshToken: The new refresh token
//   - refreshJWTID: The ID of the new refresh token
//   - error: Any error that occurred during token refresh
func (s *JWTService) RefreshTokens(refreshToken, userID int64, username, email string) (string, string, string, string, error) {
	// Validate the refresh token
	claims, err := s.ValidateToken(strconv.FormatInt(refreshToken, 10), constants.TokenTypeRefresh)
	if err != nil {
		return "", "", "", "", err
	}

	// Check if the user ID matches for additional security
	if claims.UserID != userID {
		return "", "", "", "", utils.NewInvalidTokenError()
	}

	// Generate new access token
	accessToken, accessJWTID, err := s.GenerateAccessToken(userID, username, email)
	if err != nil {
		return "", "", "", "", err
	}

	// Generate new refresh token
	newRefreshToken, refreshJWTID, err := s.GenerateRefreshToken(userID, username, email)
	if err != nil {
		return "", "", "", "", err
	}

	return accessToken, accessJWTID, newRefreshToken, refreshJWTID, nil
}
