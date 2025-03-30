package auth

import (
	"errors"
	"fmt"
	"strconv"
	"time"

	"github.com/golang-jwt/jwt/v4"
	"github.com/google/uuid"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// JWT errors
var (
	ErrInvalidToken         = errors.New("invalid token")
	ErrExpiredToken         = errors.New("token has expired")
	ErrInvalidSigningMethod = errors.New("invalid signing method")
	ErrInvalidTokenClaims   = errors.New("invalid token claims")
)

// CustomClaims represents the claims in a JWT token
type CustomClaims struct {
	UserID    int64  `json:"user_id"`
	Username  string `json:"username"`
	Email     string `json:"email"`
	TokenType string `json:"token_type"` // "access" or "refresh"
	jwt.RegisteredClaims
}

// JWTService provides JWT token generation and validation functionality
type JWTService struct {
	Config *config.JWTSettings
	config *config.JWTSettings
}

// NewJWTService creates a new JWTService instance
func NewJWTService(config *config.JWTSettings) *JWTService {
	return &JWTService{
		Config: config,
	}
}

func (s *JWTService) GetConfig() *config.JWTSettings {
	if s.Config == nil {
		return &config.JWTSettings{
			Expiry:        15 * time.Hour,
			RefreshExpiry: 7 * 24 * time.Hour,
			Issuer:        "hideme-api",
		}
	}
	return s.Config
}

// GenerateAccessToken generates a new JWT access token for a user
func (s *JWTService) GenerateAccessToken(userID int64, username, email string) (string, string, error) {
	return s.generateToken(userID, username, email, "access", s.Config.Expiry)
}

// GenerateRefreshToken generates a new JWT refresh token for a user
func (s *JWTService) GenerateRefreshToken(userID int64, username, email string) (string, string, error) {
	return s.generateToken(userID, username, email, "refresh", s.Config.RefreshExpiry)
}

// generateToken creates a new JWT token with the provided parameters
func (s *JWTService) generateToken(userID int64, username, email, tokenType string, expiry time.Duration) (string, string, error) {
	// Generate a unique token ID
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

	// Create the token
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)

	// Sign the token with the secret key
	tokenString, err := token.SignedString([]byte(s.Config.Secret))
	if err != nil {
		return "", "", fmt.Errorf("failed to sign token: %w", err)
	}

	return string(tokenString), jwtID, nil
}

// ValidateToken validates a JWT token and returns its claims if valid
func (s *JWTService) ValidateToken(tokenString string, expectedType string) (*CustomClaims, error) {
	// Parse the token
	token, err := jwt.ParseWithClaims(tokenString, &CustomClaims{}, func(token *jwt.Token) (interface{}, error) {
		// Validate the signing method
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, ErrInvalidSigningMethod
		}
		return []byte(s.Config.Secret), nil
	})

	// Handle parsing errors
	if err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return nil, utils.NewExpiredTokenError()
		}
		return nil, utils.NewInvalidTokenError()
	}

	// Check if the token is valid
	if !token.Valid {
		return nil, utils.NewInvalidTokenError()
	}

	// Extract and validate the claims
	claims, ok := token.Claims.(*CustomClaims)
	if !ok {
		return nil, utils.NewInvalidTokenError()
	}

	// Validate the token type
	if claims.TokenType != expectedType {
		return nil, utils.NewInvalidTokenError()
	}

	return claims, nil
}

// ParseTokenWithoutValidation parses a token without validating it to extract the JWT ID
// This is useful for token revocation when we need the ID even if the token has expired
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

// ExtractUserIDFromToken extracts the user ID from a token string
func (s *JWTService) ExtractUserIDFromToken(tokenString string) (int64, error) {
	claims, err := s.ValidateToken(tokenString, "access")
	if err != nil {
		return 0, err
	}
	return claims.UserID, nil
}

// RefreshTokens validates a refresh token and issues new access and refresh tokens
func (s *JWTService) RefreshTokens(refreshToken, userID int64, username, email string) (string, string, string, string, error) {
	// Validate the refresh token
	claims, err := s.ValidateToken(strconv.FormatInt(refreshToken, 10), "refresh")
	if err != nil {
		return "", "", "", "", err
	}

	// Check if the user ID matches
	if claims.UserID != userID {
		return "", "", "", "", utils.NewInvalidTokenError()
	}

	// Generate new tokens
	accessToken, accessJWTID, err := s.GenerateAccessToken(userID, username, email)
	if err != nil {
		return "", "", "", "", err
	}

	newRefreshToken, refreshJWTID, err := s.GenerateRefreshToken(userID, username, email)
	if err != nil {
		return "", "", "", "", err
	}

	return accessToken, accessJWTID, newRefreshToken, refreshJWTID, nil
}
