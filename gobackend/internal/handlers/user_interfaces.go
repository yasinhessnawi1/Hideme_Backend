// user_interfaces.go

// Package handlers provides HTTP request handlers and service interfaces for the HideMe application.
// This file defines service interfaces related to user management and authentication,
// establishing clear contracts between handlers and service implementations.
// The interfaces follow the dependency injection pattern, allowing for more modular code
// and easier testing through mocked implementations.
package handlers

import (
	"context"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

// UserServiceInterface defines the methods required from UserService.
// This interface encapsulates user management operations, allowing handlers
// to interact with user data without depending on specific implementations.
// Implementations of this interface must handle proper error reporting and
// security considerations for user operations.
type UserServiceInterface interface {
	// GetUserByID retrieves a user by their unique identifier.
	//
	// Parameters:
	//   - ctx: The context for the operation, which may include deadlines or cancellation
	//   - id: The unique identifier of the user to retrieve
	//
	// Returns:
	//   - The user if found
	//   - An error if the user doesn't exist or if database access fails
	GetUserByID(ctx context.Context, id int64) (*models.User, error)

	// UpdateUser modifies a user's information based on the provided update data.
	//
	// Parameters:
	//   - ctx: The context for the operation, which may include deadlines or cancellation
	//   - id: The unique identifier of the user to update
	//   - update: The data to update, which may include username, email, or other fields
	//
	// Returns:
	//   - The updated user after changes are applied
	//   - An error if the user doesn't exist, if validation fails, or if database access fails
	//
	// Security considerations: Implementations should validate the updated data and
	// ensure that critical fields like password are handled securely.
	UpdateUser(ctx context.Context, id int64, update *models.UserUpdate) (*models.User, error)

	// ChangePassword updates a user's password after proper validation.
	//
	// Parameters:
	//   - ctx: The context for the operation, which may include deadlines or cancellation
	//   - id: The unique identifier of the user whose password will be changed
	//   - currentPassword: The current password for verification
	//   - newPassword: The new password to set for the user
	//
	// Returns:
	//   - An error if the user doesn't exist, if password validation fails, or if database access fails
	//
	// Security considerations: Implementations must properly hash and salt the new password
	// before storing it, and should enforce password complexity requirements.
	ChangePassword(ctx context.Context, id int64, currentPassword, newPassword string) error

	// DeleteUser removes a user account and associated data.
	//
	// Parameters:
	//   - ctx: The context for the operation, which may include deadlines or cancellation
	//   - id: The unique identifier of the user to delete
	//
	// Returns:
	//   - An error if the user doesn't exist or if database access fails
	//
	// Security considerations: Implementations should ensure proper authorization
	// before deletion and should handle cascading deletions of related data.
	DeleteUser(ctx context.Context, id int64) error

	// CheckUsername verifies if a username is available for registration.
	//
	// Parameters:
	//   - ctx: The context for the operation, which may include deadlines or cancellation
	//   - username: The username to check for availability
	//
	// Returns:
	//   - true if the username is available, false if it's already taken
	//   - An error if database access fails
	CheckUsername(ctx context.Context, username string) (bool, error)

	// CheckEmail verifies if an email address is available for registration.
	//
	// Parameters:
	//   - ctx: The context for the operation, which may include deadlines or cancellation
	//   - email: The email address to check for availability
	//
	// Returns:
	//   - true if the email is available, false if it's already taken
	//   - An error if database access fails
	CheckEmail(ctx context.Context, email string) (bool, error)

	// GetUserActiveSessions retrieves all active sessions for a user.
	//
	// Parameters:
	//   - ctx: The context for the operation, which may include deadlines or cancellation
	//   - userID: The unique identifier of the user whose sessions to retrieve
	//
	// Returns:
	//   - A slice of active session information objects
	//   - An error if the user doesn't exist or if database access fails
	//
	// This method supports security features that allow users to monitor
	// and manage their authenticated sessions across devices.
	GetUserActiveSessions(ctx context.Context, userID int64) ([]*models.ActiveSessionInfo, error)

	// InvalidateSession terminates a specific user session.
	//
	// Parameters:
	//   - ctx: The context for the operation, which may include deadlines or cancellation
	//   - userID: The unique identifier of the user who owns the session
	//   - sessionID: The unique identifier of the session to invalidate
	//
	// Returns:
	//   - An error if the session doesn't exist, doesn't belong to the user, or if database access fails
	//
	// This method enables the "logout from specific device" feature, enhancing
	// security by allowing users to terminate suspicious sessions.
	InvalidateSession(ctx context.Context, userID int64, sessionID string) error
}
