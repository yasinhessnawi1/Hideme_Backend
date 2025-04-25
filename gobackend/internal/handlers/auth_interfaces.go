// Package handlers provides HTTP request handlers for the HideMe API.
package handlers

import (
	"context"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

// AuthServiceInterface defines the methods required from the authentication service.
// This interface is used by the auth handlers to interact with the authentication business logic
// without being tightly coupled to the implementation.
type AuthServiceInterface interface {
	// RegisterUser registers a new user with the provided registration data.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - reg: User registration data including username, email, and password
	//
	// Returns:
	//   - The newly created user if successful
	//   - An error if registration fails (e.g., duplicate username/email)
	RegisterUser(ctx context.Context, reg *models.UserRegistration) (*models.User, error)

	// AuthenticateUser authenticates a user with the provided credentials.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - creds: User credentials (username/email and password)
	//
	// Returns:
	//   - The authenticated user
	//   - Access token for API calls
	//   - Refresh token for obtaining new access tokens
	//   - An error if authentication fails
	AuthenticateUser(ctx context.Context, creds *models.UserCredentials) (*models.User, string, string, error)

	// RefreshTokens uses a refresh token to generate new access and refresh tokens.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - refreshToken: The current refresh token
	//
	// Returns:
	//   - New access token
	//   - New refresh token
	//   - An error if the refresh operation fails (e.g., token expired)
	RefreshTokens(ctx context.Context, refreshToken string) (string, string, error)

	// Logout invalidates the specified refresh token.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - refreshToken: The refresh token to invalidate
	//
	// Returns:
	//   - An error if the logout operation fails
	Logout(ctx context.Context, refreshToken string) error

	// LogoutAll invalidates all refresh tokens for the specified user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user whose tokens should be invalidated
	//
	// Returns:
	//   - An error if the operation fails
	LogoutAll(ctx context.Context, userID int64) error

	// CreateAPIKey generates a new API key for the specified user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user who will own the API key
	//   - name: A human-readable name for the API key
	//   - duration: How long the API key should remain valid
	//
	// Returns:
	//   - The raw API key string that should be shown to the user (only once)
	//   - The API key model containing metadata (ID, expiry date, etc.)
	//   - An error if the operation fails
	CreateAPIKey(ctx context.Context, userID int64, name string, duration time.Duration) (string, *models.APIKey, error)

	// ListAPIKeys returns all API keys for the specified user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user whose API keys to list
	//
	// Returns:
	//   - A slice of API key models (without the raw key values)
	//   - An error if the operation fails
	ListAPIKeys(ctx context.Context, userID int64) ([]*models.APIKey, error)

	// DeleteAPIKey revokes an API key owned by the specified user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user who owns the API key
	//   - keyID: The ID of the API key to delete
	//
	// Returns:
	//   - An error if the operation fails (e.g., key not found or not owned by user)
	DeleteAPIKey(ctx context.Context, userID int64, keyID string) error

	// VerifyAPIKey validates an API key and returns the associated user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - apiKeyString: The raw API key to verify
	//
	// Returns:
	//   - The user associated with the API key if valid
	//   - An error if the API key is invalid, expired, or not found
	VerifyAPIKey(ctx context.Context, apiKeyString string) (*models.User, error)

	// CleanupExpiredSessions removes expired session records.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//
	// Returns:
	//   - The number of sessions removed
	//   - An error if the cleanup operation fails
	CleanupExpiredSessions(ctx context.Context) (int64, error)

	// CleanupExpiredAPIKeys removes expired API key records.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//
	// Returns:
	//   - The number of API keys removed
	//   - An error if the cleanup operation fails
	CleanupExpiredAPIKeys(ctx context.Context) (int64, error)
}

// JWTServiceInterface defines the methods required from the JWT service.
// This interface is used by the auth handlers to interact with JWT operations
// without being tightly coupled to the implementation.
type JWTServiceInterface interface {
	// ValidateToken validates a JWT token and returns its claims.
	//
	// Parameters:
	//   - tokenString: The JWT token string to validate
	//   - expectedType: The expected token type (e.g., "access" or "refresh")
	//
	// Returns:
	//   - The token claims if validation succeeds
	//   - An error if validation fails (e.g., expired token, invalid signature)
	ValidateToken(tokenString string, expectedType string) (*auth.CustomClaims, error)

	// GetConfig returns the JWT settings configuration.
	//
	// Returns:
	//   - The JWT configuration settings including expiry times and secret
	GetConfig() *config.JWTSettings
}
