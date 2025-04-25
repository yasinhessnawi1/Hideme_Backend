// Package service provides business logic and service implementations.
//
// This package implements the application's core business logic, connecting
// repositories with API handlers and enforcing business rules. The service layer
// handles operations such as user management, authentication, and session handling
// while ensuring proper validation, security, and data consistency.
package service

import (
	"context"
	"fmt"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// UserService handles user-related operations.
// It provides methods for user management, account operations,
// and session handling.
type UserService struct {
	userRepo    repository.UserRepository
	sessionRepo repository.SessionRepository
	apiKeyRepo  repository.APIKeyRepository
	passwordCfg *auth.PasswordConfig
}

// NewUserService creates a new UserService.
//
// Parameters:
//   - userRepo: Repository for user data operations
//   - sessionRepo: Repository for session management
//   - apiKeyRepo: Repository for API key management
//   - passwordCfg: Configuration for password hashing and validation
//
// Returns:
//   - *UserService: A configured user service
func NewUserService(
	userRepo repository.UserRepository,
	sessionRepo repository.SessionRepository,
	apiKeyRepo repository.APIKeyRepository,
	passwordCfg *auth.PasswordConfig,
) *UserService {
	return &UserService{
		userRepo:    userRepo,
		sessionRepo: sessionRepo,
		apiKeyRepo:  apiKeyRepo,
		passwordCfg: passwordCfg,
	}
}

// GetUserByID retrieves a user by ID.
// Sensitive fields are sanitized before returning the user object.
//
// Parameters:
//   - ctx: Context for the database operation
//   - id: The user ID to retrieve
//
// Returns:
//   - *models.User: The user object with sensitive fields sanitized
//   - error: Any error encountered or nil if successful
func (s *UserService) GetUserByID(ctx context.Context, id int64) (*models.User, error) {
	user, err := s.userRepo.GetByID(ctx, id)
	if err != nil {
		return nil, err
	}
	return user.Sanitize(), nil
}

// UpdateUser updates a user's profile information.
// It validates changes and checks for uniqueness constraints on username and email.
//
// Parameters:
//   - ctx: Context for the database operation
//   - id: The ID of the user to update
//   - update: The user update data containing fields to change
//
// Returns:
//   - *models.User: The updated user object with sensitive fields sanitized
//   - error: Any error encountered or nil if successful
func (s *UserService) UpdateUser(ctx context.Context, id int64, update *models.UserUpdate) (*models.User, error) {
	// Get the existing user
	user, err := s.userRepo.GetByID(ctx, id)
	if err != nil {
		return nil, err
	}

	// Validate updates
	changes := false

	// Update username if provided
	if update.Username != "" && update.Username != user.Username {
		// Check if username is already taken
		exists, err := s.userRepo.ExistsByUsername(ctx, update.Username)
		if err != nil {
			return nil, fmt.Errorf("failed to check username existence: %w", err)
		}
		if exists {
			return nil, utils.NewDuplicateError("User", "username", update.Username)
		}

		user.Username = update.Username
		changes = true
	}

	// Update email if provided
	if update.Email != "" && update.Email != user.Email {
		// Check if email is already taken
		exists, err := s.userRepo.ExistsByEmail(ctx, update.Email)
		if err != nil {
			return nil, fmt.Errorf("failed to check email existence: %w", err)
		}
		if exists {
			return nil, utils.NewDuplicateError("User", "email", update.Email)
		}

		user.Email = update.Email
		changes = true
	}

	// Update password if provided
	if update.Password != "" {
		if err := s.ChangePassword(ctx, id, update.Password); err != nil {
			return nil, err
		}
		// Password is updated in a separate transaction, no need to set changes flag
	}

	// Save updates if any changes were made
	if changes {
		if err := s.userRepo.Update(ctx, user); err != nil {
			return nil, fmt.Errorf("failed to update user: %w", err)
		}
		log.Info().
			Int64("user_id", user.ID).
			Str("category", constants.LogCategoryUser).
			Str("event", constants.LogEventUserUpdate).
			Msg("User profile updated")
	}

	return user.Sanitize(), nil
}

// ChangePassword updates a user's password.
// It validates the password, hashes it, and invalidates all existing sessions
// for security.
//
// Parameters:
//   - ctx: Context for the database operation
//   - id: The user ID whose password is being changed
//   - newPassword: The new password (in plaintext)
//
// Returns:
//   - error: Any error encountered or nil if successful
func (s *UserService) ChangePassword(ctx context.Context, id int64, newPassword string) error {
	// Validate password
	if err := utils.ValidatePassword(newPassword); err != nil {
		return err
	}

	// Hash the new password
	passwordHash, salt, err := auth.HashPassword(newPassword, s.passwordCfg)
	if err != nil {
		return fmt.Errorf("failed to hash password: %w", err)
	}

	// Update the password in the database
	if err := s.userRepo.ChangePassword(ctx, id, passwordHash, salt); err != nil {
		return fmt.Errorf("failed to change password: %w", err)
	}

	// Invalidate all existing sessions for security
	if err := s.sessionRepo.DeleteByUserID(ctx, id); err != nil {
		log.Error().
			Err(err).
			Int64("user_id", id).
			Msg("Failed to invalidate sessions after password change")
	}

	log.Info().
		Int64("user_id", id).
		Str("category", constants.LogCategoryAuth).
		Msg("User password changed")

	return nil
}

// DeleteUser permanently removes a user account and all associated data.
// This is a destructive operation that will cascade delete all user-related
// data in the system.
//
// Parameters:
//   - ctx: Context for the database operation
//   - id: The ID of the user to delete
//
// Returns:
//   - error: Any error encountered or nil if successful
func (s *UserService) DeleteUser(ctx context.Context, id int64) error {
	// Delete all sessions
	if err := s.sessionRepo.DeleteByUserID(ctx, id); err != nil {
		log.Error().
			Err(err).
			Int64("user_id", id).
			Msg("Failed to delete user sessions during account deletion")
	}

	// Delete all API keys
	if err := s.apiKeyRepo.DeleteByUserID(ctx, id); err != nil {
		log.Error().
			Err(err).
			Int64("user_id", id).
			Msg("Failed to delete user API keys during account deletion")
	}

	// Delete the user
	if err := s.userRepo.Delete(ctx, id); err != nil {
		return fmt.Errorf("failed to delete user: %w", err)
	}

	log.Info().
		Int64("user_id", id).
		Str("category", constants.LogCategoryUser).
		Msg("User account deleted")

	return nil
}

// CheckUsername verifies if a username is available.
// It validates the username format and checks for uniqueness.
//
// Parameters:
//   - ctx: Context for the database operation
//   - username: The username to check
//
// Returns:
//   - bool: True if the username is available, false if it's taken
//   - error: Any error encountered or nil if successful
func (s *UserService) CheckUsername(ctx context.Context, username string) (bool, error) {
	// Validate username format
	if err := utils.ValidateUsername(username); err != nil {
		return false, err
	}

	// Check if username exists
	exists, err := s.userRepo.ExistsByUsername(ctx, username)
	if err != nil {
		return false, fmt.Errorf("failed to check username availability: %w", err)
	}

	return !exists, nil
}

// CheckEmail verifies if an email is available.
// It validates the email format and checks for uniqueness.
//
// Parameters:
//   - ctx: Context for the database operation
//   - email: The email to check
//
// Returns:
//   - bool: True if the email is available, false if it's taken
//   - error: Any error encountered or nil if successful
func (s *UserService) CheckEmail(ctx context.Context, email string) (bool, error) {
	// Validate email format
	if !utils.IsValidEmail(email) {
		return false, utils.NewValidationError("email", "Invalid email format")
	}

	// Check if email exists
	exists, err := s.userRepo.ExistsByEmail(ctx, email)
	if err != nil {
		return false, fmt.Errorf("failed to check email availability: %w", err)
	}

	return !exists, nil
}

// GetUserActiveSessions retrieves all active sessions for a user.
// This allows users to see and manage their login sessions.
//
// Parameters:
//   - ctx: Context for the database operation
//   - userID: The ID of the user whose sessions to retrieve
//
// Returns:
//   - []*models.ActiveSessionInfo: A slice of active session information
//   - error: Any error encountered or nil if successful
func (s *UserService) GetUserActiveSessions(ctx context.Context, userID int64) ([]*models.ActiveSessionInfo, error) {
	// Get all active sessions
	sessions, err := s.sessionRepo.GetActiveByUserID(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to get active sessions: %w", err)
	}

	// Convert to ActiveSessionInfo for the response
	result := make([]*models.ActiveSessionInfo, len(sessions))
	for i, session := range sessions {
		result[i] = &models.ActiveSessionInfo{
			ID:        session.ID,
			CreatedAt: session.CreatedAt,
			ExpiresAt: session.ExpiresAt,
		}
	}

	return result, nil
}

// InvalidateSession invalidates a specific session.
// This allows users to log out from a specific device or session.
// The method verifies that the session belongs to the user before invalidating it.
//
// Parameters:
//   - ctx: Context for the database operation
//   - userID: The ID of the user who owns the session
//   - sessionID: The ID of the session to invalidate
//
// Returns:
//   - error: Any error encountered or nil if successful
func (s *UserService) InvalidateSession(ctx context.Context, userID int64, sessionID string) error {
	// Get the session to verify ownership
	session, err := s.sessionRepo.GetByID(ctx, sessionID)
	if err != nil {
		return err
	}

	// Verify that the session belongs to the user
	if session.UserID != userID {
		return utils.NewForbiddenError(constants.MsgAccessDenied)
	}

	// Delete the session
	if err := s.sessionRepo.Delete(ctx, sessionID); err != nil {
		return fmt.Errorf("failed to invalidate session: %w", err)
	}

	log.Info().
		Str("session_id", sessionID).
		Int64("user_id", userID).
		Str("category", constants.LogCategoryAuth).
		Msg("Session invalidated")

	return nil
}
