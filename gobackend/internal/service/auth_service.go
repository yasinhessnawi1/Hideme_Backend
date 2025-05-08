// Package service provides business logic implementations for the HideMe application.
// It contains services that orchestrate operations across repositories and implement
// the core application functionality.
//
// This file implements the authentication service, which handles user registration,
// authentication, token management, and API key operations. The service follows
// security best practices for password handling, token validation, and session management.
package service

import (
	"context"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// AuthService handles authentication operations for the application.
// It provides methods for user registration, login, token management,
// session tracking, and API key operations, with a focus on security
// and proper credential handling.
type AuthService struct {
	userRepo    repository.UserRepository
	sessionRepo repository.SessionRepository
	apiKeyRepo  repository.APIKeyRepository
	jwtService  *auth.JWTService
	passwordCfg *auth.PasswordConfig
	apiKeyCfg   *config.APIKeySettings
}

// NewAuthService creates a new AuthService with the specified dependencies.
//
// Parameters:
//   - userRepo: Repository for user data operations
//   - sessionRepo: Repository for session management
//   - apiKeyRepo: Repository for API key operations
//   - jwtService: Service for JWT token generation and validation
//   - passwordCfg: Configuration for password hashing and validation
//   - apiKeyCfg: Configuration for API key generation and validation
//
// Returns:
//   - A new AuthService instance with all dependencies initialized
//
// The auth service requires all these dependencies to properly manage
// user authentication, session tracking, and API key operations.
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

// RegisterUser creates a new user account with provided registration information.
//
// Parameters:
//   - ctx: Context for the operation
//   - reg: Registration data including username, email, password, and confirmation
//
// Returns:
//   - The created user (sanitized) if registration succeeds
//   - ValidationError if passwords don't match or validation fails
//   - DuplicateError if username or email is already taken
//   - Other errors for database or hashing issues
//
// The method performs several validation steps:
// 1. Verifies password and confirmation match
// 2. Checks for existing users with the same username or email
// 3. Securely hashes the password with a unique salt
// 4. Creates and stores the new user record
func (s *AuthService) RegisterUser(ctx context.Context, reg *models.UserRegistration) (*models.User, error) {
	// Validate password match
	if reg.Password != reg.ConfirmPassword {
		return nil, utils.NewValidationError("confirm_password", constants.MsgPasswordsDoNotMatch)
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
	user := models.NewUser(reg.Username, reg.Email, constants.RoleUser)
	user.PasswordHash = passwordHash
	user.Salt = salt

	// Save the user to the database
	if err := s.userRepo.Create(ctx, user); err != nil {
		return nil, fmt.Errorf("failed to create user: %w", err)
	}

	// Log successful registration (using existing utility function that now integrates with GDPR)
	utils.LogAuth(constants.LogEventRegister, fmt.Sprintf("%d", user.ID), user.Username, true, "")

	return user.Sanitize(), nil
}

// AuthenticateUser verifies user credentials and returns authentication tokens.
//
// Parameters:
//   - ctx: Context for the operation
//   - creds: User credentials containing username/email and password
//
// Returns:
//   - The authenticated user (sanitized)
//   - Access token for API authorization
//   - Refresh token for obtaining new access tokens
//   - InvalidCredentialsError if authentication fails
//   - ValidationError if neither username nor email is provided
//   - Other errors for database or token generation issues
//
// The method performs the following operations:
// 1. Locates the user by username or email
// 2. Verifies the provided password against the stored hash
// 3. Generates access and refresh tokens
// 4. Creates a session record for the refresh token
// 5. Logs the successful authentication
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
			utils.LogAuth(constants.LogEventLogin, "0", creds.Username, false, "user not found")
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
		utils.LogAuth(constants.LogEventLogin, fmt.Sprintf("%d", user.ID), user.Username, false, constants.MsgInvalidPassword)
		return nil, "", "", utils.NewInvalidCredentialsError()
	}

	// Generate JWT tokens
	accessToken, _, err := s.jwtService.GenerateAccessToken(user.ID, user.Username, user.Email, user.Role)
	if err != nil {
		return nil, "", "", fmt.Errorf("failed to generate access token: %w", err)
	}

	refreshToken, refreshJWTID, err := s.jwtService.GenerateRefreshToken(user.ID, user.Username, user.Email, user.Role)
	if err != nil {
		return nil, "", "", fmt.Errorf("failed to generate refresh token: %w", err)
	}

	// Create a session for the refresh token
	session := models.NewSession(user.ID, refreshJWTID, s.jwtService.Config.RefreshExpiry)
	if err := s.sessionRepo.Create(ctx, session); err != nil {
		return nil, "", "", fmt.Errorf("failed to create session: %w", err)
	}

	utils.LogAuth(constants.LogEventLogin, fmt.Sprintf("%d", user.ID), user.Username, true, "")

	return user.Sanitize(), accessToken, refreshToken, nil
}

// RefreshTokens validates a refresh token and generates new tokens.
//
// Parameters:
//   - ctx: Context for the operation
//   - refreshToken: The refresh token to validate
//
// Returns:
//   - A new access token
//   - A new refresh token
//   - InvalidTokenError if the token is invalid or expired
//   - Other errors for database or token generation issues
//
// The method performs the following operations:
// 1. Extracts the JWT ID from the refresh token
// 2. Verifies the token exists in the active sessions
// 3. Validates the token's signature and claims
// 4. Retrieves the associated user
// 5. Deletes the old session
// 6. Generates new access and refresh tokens
// 7. Creates a new session for the new refresh token
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
	claims, err := s.jwtService.ValidateToken(refreshToken, constants.TokenTypeRefresh)
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
	accessToken, _, err := s.jwtService.GenerateAccessToken(user.ID, user.Username, user.Email, user.Role)
	if err != nil {
		return "", "", fmt.Errorf("failed to generate access token: %w", err)
	}

	newRefreshToken, refreshJWTID, err := s.jwtService.GenerateRefreshToken(user.ID, user.Username, user.Email, user.Role)
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

// Logout invalidates a user's session by removing the refresh token session.
//
// Parameters:
//   - ctx: Context for the operation
//   - refreshToken: The refresh token to invalidate
//
// Returns:
//   - InvalidTokenError if the token cannot be parsed
//   - Other errors for database issues
//   - nil on successful logout or if the session was already invalidated
//
// The method performs the following operations:
// 1. Extracts the JWT ID from the refresh token
// 2. Deletes the session associated with the JWT ID
// 3. Returns success even if the session was already deleted (idempotent)
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

// LogoutAll invalidates all of a user's sessions.
// This is a security feature that allows users to terminate all active sessions
// across all devices, useful in case of a suspected security breach.
//
// Parameters:
//   - ctx: Context for the operation
//   - userID: The ID of the user whose sessions should be invalidated
//
// Returns:
//   - An error if session deletion fails
//   - nil on successful invalidation of all sessions
func (s *AuthService) LogoutAll(ctx context.Context, userID int64) error {
	// Delete all sessions for the user
	if err := s.sessionRepo.DeleteByUserID(ctx, userID); err != nil {
		return fmt.Errorf("failed to delete user sessions: %w", err)
	}

	return nil
}

// CreateAPIKey generates a new API key for a user.
//
// Parameters:
//   - ctx: Context for the operation
//   - userID: The ID of the user who will own the API key
//   - name: A human-readable name/description for the API key
//   - duration: How long the API key should remain valid
//
// Returns:
//   - The raw API key (only returned once at creation time)
//   - The API key metadata (without sensitive information)
//   - An error if key generation or storage fails
//
// The method performs the following operations:
// 1. Generates a new API key using secure random data
// 2. Creates a database record with the key's hash (not the key itself)
// 3. Logs the key creation event
// 4. Returns the raw key and metadata to the caller
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

	utils.LogAPIKey(constants.LogEventAPIKey, apiKey.ID, fmt.Sprintf("%d", userID))

	return rawKey, response, nil
}

// ListAPIKeys retrieves all API keys for a user.
//
// Parameters:
//   - ctx: Context for the operation
//   - userID: The ID of the user whose API keys should be returned
//
// Returns:
//   - A slice of API keys (without sensitive hash information)
//   - An error if retrieval fails
//
// The method sanitizes each API key to remove the hash before returning.
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

// DeleteAPIKey revokes an API key.
//
// Parameters:
//   - ctx: Context for the operation
//   - userID: The ID of the user who owns the API key
//   - keyID: The ID of the API key to delete
//
// Returns:
//   - ForbiddenError if the API key doesn't belong to the user
//   - NotFoundError if the API key doesn't exist
//   - Other errors for database issues
//   - nil on successful deletion
//
// The method verifies ownership of the API key before deletion to prevent
// unauthorized deletion of keys belonging to other users.
func (s *AuthService) DeleteAPIKey(ctx context.Context, userID int64, keyID string) error {
	// Get the API key to verify ownership
	apiKey, err := s.apiKeyRepo.GetByID(ctx, keyID)
	if err != nil {
		return err
	}

	// Verify that the API key belongs to the user
	if apiKey.UserID != userID {
		return utils.NewForbiddenError(constants.MsgAccessDenied)
	}

	// Delete the API key
	if err := s.apiKeyRepo.Delete(ctx, keyID); err != nil {
		return fmt.Errorf("failed to delete API key: %w", err)
	}

	utils.LogAPIKey("deleted", keyID, fmt.Sprintf("%d", userID))

	return nil
}

func (s *AuthService) VerifyAPIKey(ctx context.Context, apiKeyString string) (*models.User, error) {
	// No need to parse the API key - just use the entire string for validation

	// Get all API keys
	apiKeys, err := s.apiKeyRepo.GetAll(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to get API keys: %w", err)
	}

	// Get the encryption key from the config
	var encryptionKey []byte
	if s.apiKeyCfg != nil && s.apiKeyCfg.EncryptionKey != "" {
		encryptionKey = []byte(s.apiKeyCfg.EncryptionKey)
	}

	// Check each API key
	for _, apiKey := range apiKeys {
		// Skip expired keys
		if time.Now().After(apiKey.ExpiresAt) {
			continue
		}

		// Check if the stored key is encrypted
		if auth.IsEncrypted(apiKey.APIKeyHash) {
			// Try to decrypt
			decryptedKey, err := auth.DecryptAPIKey(apiKey.APIKeyHash, encryptionKey)
			if err == nil && decryptedKey == apiKeyString {
				// Found a match
				user, err := s.userRepo.GetByID(ctx, apiKey.UserID)
				if err != nil {
					return nil, fmt.Errorf("failed to get user for API key: %w", err)
				}
				utils.LogAPIKey("verified", apiKey.ID, fmt.Sprintf("%d", user.ID))
				return user.Sanitize(), nil
			}
		} else {
			// Fall back to hash comparison
			hashedKey := auth.HashAPIKey(apiKeyString, nil) // nil forces hash mode
			if hashedKey == apiKey.APIKeyHash {
				user, err := s.userRepo.GetByID(ctx, apiKey.UserID)
				if err != nil {
					return nil, fmt.Errorf("failed to get user for API key: %w", err)
				}
				utils.LogAPIKey("verified", apiKey.ID, fmt.Sprintf("%d", user.ID))
				return user.Sanitize(), nil
			}
		}
	}

	return nil, utils.NewInvalidTokenError()
}

// GetDecryptedAPIKey retrieves an API key by its ID and decrypts it if encrypted.
// This is a privileged operation that should only be accessible to authenticated users
// for their own API keys.
//
// Parameters:
//   - ctx: Context for the operation
//   - userID: The ID of the user requesting the key (for authorization)
//   - keyID: The ID of the API key to retrieve
//
// Returns:
//   - The API key model with the decrypted original key
//   - ForbiddenError if the key doesn't belong to the user
//   - NotFoundError if the key doesn't exist
//   - Other errors for database or decryption issues
func (s *AuthService) GetDecryptedAPIKey(ctx context.Context, userID int64, keyID string) (*models.APIKey, string, error) {
	// Get the API key
	apiKey, err := s.apiKeyRepo.GetByID(ctx, keyID)
	if err != nil {
		return nil, "", err
	}

	// Verify that the API key belongs to the user
	if apiKey.UserID != userID {
		return nil, "", utils.NewForbiddenError(constants.MsgAccessDenied)
	}

	// Check if the API key has expired
	if apiKey.IsExpired() {
		return nil, "", utils.NewExpiredTokenError()
	}

	// Get the encryption key
	var encryptionKey []byte
	if s.apiKeyCfg != nil && s.apiKeyCfg.EncryptionKey != "" {
		encryptionKey = []byte(s.apiKeyCfg.EncryptionKey)
	}

	// Try to decode the API key
	var originalKey string
	if auth.IsEncrypted(apiKey.APIKeyHash) {
		// API key is encrypted with AES-256-GCM
		originalKey, err = auth.DecryptAPIKey(apiKey.APIKeyHash, encryptionKey)
		if err != nil {
			return nil, "", fmt.Errorf("failed to decrypt API key: %w", err)
		}
	} else {
		// API key is hashed (not reversible)
		return nil, "", fmt.Errorf("API key is hashed and cannot be decrypted")
	}

	return apiKey, originalKey, nil
}

// CleanupExpiredSessions removes expired sessions from the database.
// This is typically called periodically as a maintenance task.
//
// Parameters:
//   - ctx: Context for the operation
//
// Returns:
//   - The number of expired sessions deleted
//   - An error if deletion fails
func (s *AuthService) CleanupExpiredSessions(ctx context.Context) (int64, error) {
	return s.sessionRepo.DeleteExpired(ctx)
}

// CleanupExpiredAPIKeys removes expired API keys from the database.
// This is typically called periodically as a maintenance task.
//
// Parameters:
//   - ctx: Context for the operation
//
// Returns:
//   - The number of expired API keys deleted
//   - An error if deletion fails
func (s *AuthService) CleanupExpiredAPIKeys(ctx context.Context) (int64, error) {
	return s.apiKeyRepo.DeleteExpired(ctx)
}
