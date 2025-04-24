package service

import (
	"context"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// AuthService handles authentication operations
type AuthService struct {
	userRepo    repository.UserRepository
	sessionRepo repository.SessionRepository
	apiKeyRepo  repository.APIKeyRepository
	jwtService  *auth.JWTService
	passwordCfg *auth.PasswordConfig
	apiKeyCfg   *config.APIKeySettings
}

// NewAuthService creates a new AuthService
func NewAuthService(
	userRepo repository.UserRepository,
	sessionRepo repository.SessionRepository,
	apiKeyRepo repository.APIKeyRepository,
	jwtService *auth.JWTService,
	passwordCfg *auth.PasswordConfig,
	apiKeyCfg *config.APIKeySettings,
) *AuthService {
	return &AuthService{
		userRepo:    userRepo,
		sessionRepo: sessionRepo,
		apiKeyRepo:  apiKeyRepo,
		jwtService:  jwtService,
		passwordCfg: passwordCfg,
		apiKeyCfg:   apiKeyCfg,
	}
}

// RegisterUser creates a new user account
func (s *AuthService) RegisterUser(ctx context.Context, reg *models.UserRegistration) (*models.User, error) {
	// Validate password match
	if reg.Password != reg.ConfirmPassword {
		return nil, utils.NewValidationError("confirm_password", "Passwords do not match")
	}

	// Check if username already exists
	existsUsername, err := s.userRepo.ExistsByUsername(ctx, reg.Username)
	if err != nil {
		return nil, fmt.Errorf("failed to check username existence: %w", err)
	}
	if existsUsername {
		return nil, utils.NewDuplicateError("User", "username", reg.Username)
	}

	// Check if email already exists
	existsEmail, err := s.userRepo.ExistsByEmail(ctx, reg.Email)
	if err != nil {
		return nil, fmt.Errorf("failed to check email existence: %w", err)
	}
	if existsEmail {
		return nil, utils.NewDuplicateError("User", "email", reg.Email)
	}

	// Hash the password
	passwordHash, salt, err := auth.HashPassword(reg.Password, s.passwordCfg)
	if err != nil {
		return nil, fmt.Errorf("failed to hash password: %w", err)
	}

	// Create the user
	user := models.NewUser(reg.Username, reg.Email)
	user.PasswordHash = passwordHash
	user.Salt = salt

	// Save the user to the database
	if err := s.userRepo.Create(ctx, user); err != nil {
		return nil, fmt.Errorf("failed to create user: %w", err)
	}

	// Log successful registration (using existing utility function that now integrates with GDPR)
	utils.LogAuth("register_success", fmt.Sprintf("%d", user.ID), user.Username, true, "")

	return user.Sanitize(), nil
}

// AuthenticateUser verifies user credentials and returns authentication tokens
func (s *AuthService) AuthenticateUser(ctx context.Context, creds *models.UserCredentials) (*models.User, string, string, error) {
	var user *models.User
	var err error

	// Find the user by username or email
	if creds.Username != "" {
		user, err = s.userRepo.GetByUsername(ctx, creds.Username)
	} else if creds.Email != "" {
		user, err = s.userRepo.GetByEmail(ctx, creds.Email)
	} else {
		return nil, "", "", utils.NewValidationError("credentials", "Username or email is required")
	}

	if err != nil {
		if utils.IsNotFoundError(err) {
			utils.LogAuth("login_failed", "0", creds.Username, false, "user not found")
			return nil, "", "", utils.NewInvalidCredentialsError()
		}
		return nil, "", "", fmt.Errorf("failed to get user: %w", err)
	}

	// Verify the password
	match, err := auth.VerifyPassword(creds.Password, user.PasswordHash, user.Salt, s.passwordCfg)
	if err != nil {
		return nil, "", "", fmt.Errorf("failed to verify password: %w", err)
	}

	if !match {
		utils.LogAuth("login_failed", fmt.Sprintf("%d", user.ID), user.Username, false, "invalid password")
		return nil, "", "", utils.NewInvalidCredentialsError()
	}

	// Generate JWT tokens
	accessToken, _, err := s.jwtService.GenerateAccessToken(user.ID, user.Username, user.Email)
	if err != nil {
		return nil, "", "", fmt.Errorf("failed to generate access token: %w", err)
	}

	refreshToken, refreshJWTID, err := s.jwtService.GenerateRefreshToken(user.ID, user.Username, user.Email)
	if err != nil {
		return nil, "", "", fmt.Errorf("failed to generate refresh token: %w", err)
	}

	// Create a session for the refresh token
	session := models.NewSession(user.ID, refreshJWTID, s.jwtService.Config.RefreshExpiry)
	if err := s.sessionRepo.Create(ctx, session); err != nil {
		return nil, "", "", fmt.Errorf("failed to create session: %w", err)
	}

	utils.LogAuth("login_success", fmt.Sprintf("%d", user.ID), user.Username, true, "")

	return user.Sanitize(), accessToken, refreshToken, nil
}

// RefreshTokens validates a refresh token and generates new tokens
func (s *AuthService) RefreshTokens(ctx context.Context, refreshToken string) (string, string, error) {
	// Parse the refresh token without validating to get the JWT ID
	jwtID, err := s.jwtService.ParseTokenWithoutValidation(refreshToken)
	if err != nil {
		return "", "", utils.NewInvalidTokenError()
	}

	// Check if the token is in the active sessions
	isValid, err := s.sessionRepo.IsValidSession(ctx, jwtID)
	if err != nil {
		return "", "", fmt.Errorf("failed to check session validity: %w", err)
	}

	if !isValid {
		return "", "", utils.NewInvalidTokenError()
	}

	// Validate the refresh token
	claims, err := s.jwtService.ValidateToken(refreshToken, "refresh")
	if err != nil {
		// Delete the session if the token is invalid
		_ = s.sessionRepo.DeleteByJWTID(ctx, jwtID)
		return "", "", err
	}

	// Get the user from the claims
	user, err := s.userRepo.GetByID(ctx, claims.UserID)
	if err != nil {
		return "", "", fmt.Errorf("failed to get user: %w", err)
	}

	// Delete the old session
	if err := s.sessionRepo.DeleteByJWTID(ctx, jwtID); err != nil {
		log.Warn().
			Err(err).
			Str("jwt_id", jwtID).
			Msg("Failed to delete old session during token refresh")
	}

	// Generate new tokens
	accessToken, _, err := s.jwtService.GenerateAccessToken(user.ID, user.Username, user.Email)
	if err != nil {
		return "", "", fmt.Errorf("failed to generate access token: %w", err)
	}

	newRefreshToken, refreshJWTID, err := s.jwtService.GenerateRefreshToken(user.ID, user.Username, user.Email)
	if err != nil {
		return "", "", fmt.Errorf("failed to generate refresh token: %w", err)
	}

	// Create a new session for the refresh token
	session := models.NewSession(user.ID, refreshJWTID, s.jwtService.Config.RefreshExpiry)
	if err := s.sessionRepo.Create(ctx, session); err != nil {
		return "", "", fmt.Errorf("failed to create session: %w", err)
	}

	log.Info().
		Int64("user_id", user.ID).
		Str("username", user.Username).
		Msg("Tokens refreshed successfully")

	return accessToken, newRefreshToken, nil
}

// Logout invalidates a user's session
func (s *AuthService) Logout(ctx context.Context, refreshToken string) error {
	// Parse the refresh token without validating to get the JWT ID
	jwtID, err := s.jwtService.ParseTokenWithoutValidation(refreshToken)
	if err != nil {
		return utils.NewInvalidTokenError()
	}

	// Delete the session
	if err := s.sessionRepo.DeleteByJWTID(ctx, jwtID); err != nil {
		if utils.IsNotFoundError(err) {
			// If the session wasn't found, consider it already logged out
			return nil
		}
		return fmt.Errorf("failed to delete session: %w", err)
	}

	return nil
}

// LogoutAll invalidates all of a user's sessions
func (s *AuthService) LogoutAll(ctx context.Context, userID int64) error {
	// Delete all sessions for the user
	if err := s.sessionRepo.DeleteByUserID(ctx, userID); err != nil {
		return fmt.Errorf("failed to delete user sessions: %w", err)
	}

	return nil
}

// CreateAPIKey generates a new API key for a user
func (s *AuthService) CreateAPIKey(ctx context.Context, userID int64, name string, duration time.Duration) (string, *models.APIKey, error) {
	// Generate a new API key
	apiKeyService := auth.NewAPIKeyService(s.apiKeyCfg)
	apiKey, rawKey, err := apiKeyService.GenerateAPIKey(userID, name, duration)
	if err != nil {
		return "", nil, fmt.Errorf("failed to generate API key: %w", err)
	}

	// Save the API key to the database
	if err := s.apiKeyRepo.Create(ctx, apiKey); err != nil {
		return "", nil, fmt.Errorf("failed to save API key: %w", err)
	}

	// Create a response that doesn't include the hash
	response := &models.APIKey{
		ID:        apiKey.ID,
		UserID:    apiKey.UserID,
		Name:      apiKey.Name,
		ExpiresAt: apiKey.ExpiresAt,
		CreatedAt: apiKey.CreatedAt,
	}

	utils.LogAPIKey("created", apiKey.ID, fmt.Sprintf("%d", userID))

	return rawKey, response, nil
}

// ListAPIKeys retrieves all API keys for a user
func (s *AuthService) ListAPIKeys(ctx context.Context, userID int64) ([]*models.APIKey, error) {
	// Get all API keys for the user
	apiKeys, err := s.apiKeyRepo.GetByUserID(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to get API keys: %w", err)
	}

	// Remove sensitive information
	result := make([]*models.APIKey, len(apiKeys))
	for i, key := range apiKeys {
		sanitized := *key
		sanitized.APIKeyHash = ""
		result[i] = &sanitized
	}

	return result, nil
}

// DeleteAPIKey revokes an API key
func (s *AuthService) DeleteAPIKey(ctx context.Context, userID int64, keyID string) error {
	// Get the API key to verify ownership
	apiKey, err := s.apiKeyRepo.GetByID(ctx, keyID)
	if err != nil {
		return err
	}

	// Verify that the API key belongs to the user
	if apiKey.UserID != userID {
		return utils.NewForbiddenError("You do not have permission to delete this API key")
	}

	// Delete the API key
	if err := s.apiKeyRepo.Delete(ctx, keyID); err != nil {
		return fmt.Errorf("failed to delete API key: %w", err)
	}

	utils.LogAPIKey("deleted", keyID, fmt.Sprintf("%d", userID))

	return nil
}

// VerifyAPIKey verifies an API key and returns the associated user
func (s *AuthService) VerifyAPIKey(ctx context.Context, apiKeyString string) (*models.User, error) {
	// Parse the API key
	keyID, _, err := auth.ParseAPIKey(apiKeyString)
	if err != nil {
		return nil, utils.NewInvalidTokenError()
	}

	// Hash the API key
	keyHash := auth.HashAPIKey(apiKeyString)

	// Verify the API key
	apiKey, err := s.apiKeyRepo.VerifyKey(ctx, keyID, keyHash)
	if err != nil {
		return nil, err
	}

	// Get the associated user
	user, err := s.userRepo.GetByID(ctx, apiKey.UserID)
	if err != nil {
		return nil, fmt.Errorf("failed to get user for API key: %w", err)
	}

	utils.LogAPIKey("verified", keyID, fmt.Sprintf("%d", user.ID))

	return user.Sanitize(), nil
}

// CleanupExpiredSessions removes expired sessions from the database
func (s *AuthService) CleanupExpiredSessions(ctx context.Context) (int64, error) {
	return s.sessionRepo.DeleteExpired(ctx)
}

// CleanupExpiredAPIKeys removes expired API keys from the database
func (s *AuthService) CleanupExpiredAPIKeys(ctx context.Context) (int64, error) {
	return s.apiKeyRepo.DeleteExpired(ctx)
}
