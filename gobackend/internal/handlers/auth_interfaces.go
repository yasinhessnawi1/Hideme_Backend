package handlers

import (
	"context"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

// AuthServiceInterface defines the methods required from AuthService
type AuthServiceInterface interface {
	RegisterUser(ctx context.Context, reg *models.UserRegistration) (*models.User, error)
	AuthenticateUser(ctx context.Context, creds *models.UserCredentials) (*models.User, string, string, error)
	RefreshTokens(ctx context.Context, refreshToken string) (string, string, error)
	Logout(ctx context.Context, refreshToken string) error
	LogoutAll(ctx context.Context, userID int64) error
	CreateAPIKey(ctx context.Context, userID int64, name string, duration time.Duration) (string, *models.APIKey, error)
	ListAPIKeys(ctx context.Context, userID int64) ([]*models.APIKey, error)
	DeleteAPIKey(ctx context.Context, userID int64, keyID string) error
	VerifyAPIKey(ctx context.Context, apiKeyString string) (*models.User, error)
	CleanupExpiredSessions(ctx context.Context) (int64, error)
	CleanupExpiredAPIKeys(ctx context.Context) (int64, error)
}

// JWTServiceInterface defines the methods required from JWTService
type JWTServiceInterface interface {
	ValidateToken(tokenString string, expectedType string) (*auth.CustomClaims, error)
	GetConfig() *config.JWTSettings
}
