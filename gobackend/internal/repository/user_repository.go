// Package repository provides data access interfaces and implementations for the HideMe application.
// It follows the repository pattern to abstract database operations and provide a clean API
// for data persistence operations.
//
// This file implements the user repository, which manages user accounts with a focus on
// security and privacy. The repository handles secure authentication, data privacy,
// and GDPR compliance features including proper logging and masking of personal information.
package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/lib/pq"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils/gdprlog"
)

// UserRepository defines methods for interacting with user data in the database.
// It provides operations for user management including creation, retrieval, update,
// and deletion with a focus on security and privacy.
type UserRepository interface {
	// Create adds a new user to the database.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - user: The user to store, with required fields populated
	//
	// Returns:
	//   - DuplicateError if a user with the same username or email already exists
	//   - Other errors for database issues
	//   - nil on successful creation
	//
	// The user ID will be populated after successful creation.
	// This method automatically sets creation and update timestamps.
	Create(ctx context.Context, user *models.User) error

	// GetByID retrieves a user by their unique identifier.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - id: The unique identifier of the user
	//
	// Returns:
	//   - The user if found (including sensitive fields like password hash)
	//   - NotFoundError if the user doesn't exist
	//   - Other errors for database issues
	//
	// Note: The caller should use user.Sanitize() before returning to clients.
	GetByID(ctx context.Context, id int64) (*models.User, error)

	// GetByUsername retrieves a user by their username.
	// The comparison is case-insensitive for better user experience.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - username: The username to search for
	//
	// Returns:
	//   - The user if found (including sensitive fields like password hash)
	//   - NotFoundError if no user exists with the username
	//   - Other errors for database issues
	//
	// Note: The caller should use user.Sanitize() before returning to clients.
	GetByUsername(ctx context.Context, username string) (*models.User, error)

	// GetByEmail retrieves a user by their email address.
	// The comparison is case-insensitive for better user experience.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - email: The email address to search for
	//
	// Returns:
	//   - The user if found (including sensitive fields like password hash)
	//   - NotFoundError if no user exists with the email
	//   - Other errors for database issues
	//
	// Note: The caller should use user.Sanitize() before returning to clients.
	// For privacy reasons, this method avoids logging the actual email address.
	GetByEmail(ctx context.Context, email string) (*models.User, error)

	// Update updates a user in the database.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - user: The user to update
	//
	// Returns:
	//   - DuplicateError if the update would result in a unique constraint violation
	//   - NotFoundError if the user doesn't exist
	//   - Other errors for database issues
	//   - nil on successful update
	//
	// This method automatically updates the UpdatedAt timestamp.
	// It does not update password fields; use ChangePassword for that.
	Update(ctx context.Context, user *models.User) error

	// Delete removes a user from the database.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - id: The unique identifier of the user to delete
	//
	// Returns:
	//   - NotFoundError if the user doesn't exist
	//   - Other errors for database issues
	//   - nil on successful deletion
	//
	// This method uses a transaction to ensure proper deletion of related records.
	Delete(ctx context.Context, id int64) error

	// ChangePassword updates a user's password credentials.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - id: The unique identifier of the user
	//   - passwordHash: The new hashed password
	//   - salt: The new salt used in password hashing
	//
	// Returns:
	//   - NotFoundError if the user doesn't exist
	//   - Other errors for database issues
	//   - nil on successful update
	//
	// This method also updates the UpdatedAt timestamp.
	ChangePassword(ctx context.Context, id int64, passwordHash, salt string) error

	// ExistsByUsername checks if a user with the given username exists.
	// The comparison is case-insensitive for better user experience.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - username: The username to check
	//
	// Returns:
	//   - true if a user with the username exists
	//   - false if no user with the username exists
	//   - An error if the check fails
	ExistsByUsername(ctx context.Context, username string) (bool, error)

	// ExistsByEmail checks if a user with the given email exists.
	// The comparison is case-insensitive for better user experience.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - email: The email to check
	//
	// Returns:
	//   - true if a user with the email exists
	//   - false if no user with the email exists
	//   - An error if the check fails
	//
	// For privacy reasons, this method avoids logging the actual email address.
	ExistsByEmail(ctx context.Context, email string) (bool, error)
}

// PostgresUserRepository is a PostgreSQL implementation of UserRepository.
// It implements all required methods using PostgreSQL-specific features
// and error handling, with special attention to security and privacy concerns.
type PostgresUserRepository struct {
	db *database.Pool
}

// NewUserRepository creates a new UserRepository implementation for PostgreSQL.
//
// Parameters:
//   - db: A connection pool for PostgreSQL database access
//
// Returns:
//   - An implementation of the UserRepository interface
func NewUserRepository(db *database.Pool) UserRepository {
	return &PostgresUserRepository{
		db: db,
	}
}

// Create adds a new user to the database.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - user: The user to store
//
// Returns:
//   - DuplicateError if a user with the same username or email already exists
//   - Other errors for database issues
//   - nil on successful creation
//
// The user ID will be populated after successful creation.
// This method automatically sets creation and update timestamps.
func (r *PostgresUserRepository) Create(ctx context.Context, user *models.User) error {
	// Start query timer
	startTime := time.Now()

	// Set created/updated timestamps
	now := time.Now()
	user.CreatedAt = now
	user.UpdatedAt = now

	// Define the query with RETURNING for PostgreSQL
	query := `
        INSERT INTO users (username, email, password_hash, salt, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING user_id
    `

	// Execute the query
	err := r.db.QueryRowContext(
		ctx,
		query,
		user.Username,
		user.Email,
		user.PasswordHash,
		user.Salt,
		user.CreatedAt,
		user.UpdatedAt,
	).Scan(&user.ID)

	// Log the query execution with sensitive data redacted
	utils.LogDBQuery(
		query,
		[]interface{}{user.Username, user.Email, "[REDACTED]", "[REDACTED]", user.CreatedAt, user.UpdatedAt},
		time.Since(startTime),
		err,
	)

	if err != nil {
		// Check for unique constraint violations using PostgreSQL error handling
		if pqErr, ok := err.(*pq.Error); ok {
			// 23505 is the PostgreSQL error code for unique_violation
			if pqErr.Code == "23505" {
				// Check which constraint was violated
				if strings.Contains(pqErr.Constraint, "username") {
					return utils.NewDuplicateError("User", "username", user.Username)
				}
				if strings.Contains(pqErr.Constraint, "email") {
					return utils.NewDuplicateError("User", "email", user.Email)
				}
			}
		}
		return fmt.Errorf("failed to create user: %w", err)
	}

	// Log successful user creation with GDPR compliance
	if gdprLogger := utils.GetGDPRLogger(); gdprLogger != nil {
		gdprLogger.Info("User created", map[string]interface{}{
			"user_id":  user.ID,
			"username": user.Username,
			// Email is personal data, should be in personal logs with masking
			"email":    gdprlog.MaskEmail(user.Email),
			"category": gdprlog.PersonalLog,
		})
	} else {
		// Fallback to standard logging
		log.Info().
			Int64("user_id", user.ID).
			Str("username", user.Username).
			Str("email", user.Email).
			Msg("User created")
	}

	return nil
}

// GetByID retrieves a user by ID.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - id: The unique identifier of the user
//
// Returns:
//   - The user if found (including sensitive fields like password hash)
//   - NotFoundError if the user doesn't exist
//   - Other errors for database issues
func (r *PostgresUserRepository) GetByID(ctx context.Context, id int64) (*models.User, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT user_id, username, email, password_hash, salt, created_at, updated_at
        FROM users
        WHERE user_id = $1
    `

	// Execute the query
	user := &models.User{}
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&user.ID,
		&user.Username,
		&user.Email,
		&user.PasswordHash,
		&user.Salt,
		&user.CreatedAt,
		&user.UpdatedAt,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{id},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewNotFoundError("User", id)
		}
		return nil, fmt.Errorf("failed to get user by ID: %w", err)
	}

	return user, nil
}

// GetByUsername retrieves a user by username.
// The comparison is case-insensitive for better user experience.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - username: The username to search for
//
// Returns:
//   - The user if found (including sensitive fields like password hash)
//   - NotFoundError if no user exists with the username
//   - Other errors for database issues
func (r *PostgresUserRepository) GetByUsername(ctx context.Context, username string) (*models.User, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query with case-insensitive comparison for PostgreSQL
	query := `
        SELECT user_id, username, email, password_hash, salt, created_at, updated_at
        FROM users
        WHERE LOWER(username) = LOWER($1)
    `

	// Execute the query
	user := &models.User{}
	err := r.db.QueryRowContext(ctx, query, username).Scan(
		&user.ID,
		&user.Username,
		&user.Email,
		&user.PasswordHash,
		&user.Salt,
		&user.CreatedAt,
		&user.UpdatedAt,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{username},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewNotFoundError("User", fmt.Sprintf("username=%s", username))
		}
		return nil, fmt.Errorf("failed to get user by username: %w", err)
	}

	return user, nil
}

// GetByEmail retrieves a user by email.
// The comparison is case-insensitive for better user experience.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - email: The email address to search for
//
// Returns:
//   - The user if found (including sensitive fields like password hash)
//   - NotFoundError if no user exists with the email
//   - Other errors for database issues
//
// For privacy reasons, this method avoids logging the actual email address.
func (r *PostgresUserRepository) GetByEmail(ctx context.Context, email string) (*models.User, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query with case-insensitive comparison for PostgreSQL
	query := `
        SELECT user_id, username, email, password_hash, salt, created_at, updated_at
        FROM users
        WHERE LOWER(email) = LOWER($1)
    `

	// Execute the query
	user := &models.User{}
	err := r.db.QueryRowContext(ctx, query, email).Scan(
		&user.ID,
		&user.Username,
		&user.Email,
		&user.PasswordHash,
		&user.Salt,
		&user.CreatedAt,
		&user.UpdatedAt,
	)

	// Log the query execution with email redacted for GDPR compliance
	utils.LogDBQuery(
		query,
		[]interface{}{"[EMAIL-REDACTED]"}, // Don't log actual email in query parameters
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewNotFoundError("User", "email=[REDACTED]") // Don't include actual email in error
		}
		return nil, fmt.Errorf("failed to get user by email: %w", err)
	}

	return user, nil
}

// Update updates a user in the database.
// This method automatically updates the UpdatedAt timestamp.
// It does not update password fields; use ChangePassword for that.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - user: The user to update
//
// Returns:
//   - DuplicateError if the update would result in a unique constraint violation
//   - NotFoundError if the user doesn't exist
//   - Other errors for database issues
//   - nil on successful update
func (r *PostgresUserRepository) Update(ctx context.Context, user *models.User) error {
	// Start query timer
	startTime := time.Now()

	// Update the updated_at timestamp
	user.UpdatedAt = time.Now()

	// Define the query
	query := `
        UPDATE users
        SET username = $1, email = $2, updated_at = $3
        WHERE user_id = $4
    `

	// Execute the query
	result, err := r.db.ExecContext(
		ctx,
		query,
		user.Username,
		user.Email,
		user.UpdatedAt,
		user.ID,
	)

	// Log the query execution with GDPR considerations
	utils.LogDBQuery(
		query,
		[]interface{}{user.Username, "[EMAIL-REDACTED]", user.UpdatedAt, user.ID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		// Check for unique constraint violations using PostgreSQL error handling
		if pqErr, ok := err.(*pq.Error); ok {
			// 23505 is the PostgreSQL error code for unique_violation
			if pqErr.Code == "23505" {
				if strings.Contains(pqErr.Constraint, "username") {
					return utils.NewDuplicateError("User", "username", user.Username)
				}
				if strings.Contains(pqErr.Constraint, "email") {
					return utils.NewDuplicateError("User", "email", "[REDACTED]") // Don't include actual email in error
				}
			}
		}
		return fmt.Errorf("failed to update user: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("User", user.ID)
	}

	// Log successful update with GDPR compliance
	if gdprLogger := utils.GetGDPRLogger(); gdprLogger != nil {
		gdprLogger.Info("User updated", map[string]interface{}{
			"user_id":  user.ID,
			"username": user.Username,
			"email":    gdprlog.MaskEmail(user.Email),
			"category": gdprlog.PersonalLog,
		})
	} else {
		// Fallback to standard logging
		log.Info().
			Int64("user_id", user.ID).
			Str("username", user.Username).
			Str("email", user.Email).
			Msg("User updated")
	}

	return nil
}

// Delete removes a user from the database.
// This method uses a transaction to ensure proper deletion of related records.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - id: The unique identifier of the user to delete
//
// Returns:
//   - NotFoundError if the user doesn't exist
//   - Other errors for database issues
//   - nil on successful deletion
func (r *PostgresUserRepository) Delete(ctx context.Context, id int64) error {
	// Start query timer
	startTime := time.Now()

	// Execute the delete within a transaction to cascade properly
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// Delete related records first (this would be handled by foreign key cascades)

		// Finally, delete the user
		query := "DELETE FROM users WHERE user_id = $1"
		result, err := tx.ExecContext(ctx, query, id)

		// Log the query execution
		utils.LogDBQuery(
			query,
			[]interface{}{id},
			time.Since(startTime),
			err,
		)

		if err != nil {
			return fmt.Errorf("failed to delete user: %w", err)
		}

		// Check if any rows were affected
		rowsAffected, err := result.RowsAffected()
		if err != nil {
			return fmt.Errorf("failed to get rows affected: %w", err)
		}

		if rowsAffected == 0 {
			return utils.NewNotFoundError("User", id)
		}

		// Log successful deletion with GDPR compliance
		if gdprLogger := utils.GetGDPRLogger(); gdprLogger != nil {
			gdprLogger.Info("User deleted", map[string]interface{}{
				"user_id":  id,
				"category": gdprlog.PersonalLog,
			})
		} else {
			// Fallback to standard logging
			log.Info().
				Int64("user_id", id).
				Msg("User deleted")
		}

		return nil
	})
}

// ChangePassword updates a user's password credentials.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - id: The unique identifier of the user
//   - passwordHash: The new hashed password
//   - salt: The new salt used in password hashing
//
// Returns:
//   - NotFoundError if the user doesn't exist
//   - Other errors for database issues
//   - nil on successful update
//
// This method also updates the UpdatedAt timestamp.
func (r *PostgresUserRepository) ChangePassword(ctx context.Context, id int64, passwordHash, salt string) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        UPDATE users
        SET password_hash = $1, salt = $2, updated_at = $3
        WHERE user_id = $4
    `

	// Execute the query
	now := time.Now()
	result, err := r.db.ExecContext(
		ctx,
		query,
		passwordHash,
		salt,
		now,
		id,
	)

	// Log the query execution (without sensitive data)
	utils.LogDBQuery(
		query,
		[]interface{}{"[REDACTED]", "[REDACTED]", now, id},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to update password: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("User", id)
	}

	// Log password change with GDPR compliance - this is sensitive
	if gdprLogger := utils.GetGDPRLogger(); gdprLogger != nil {
		gdprLogger.Info("User password changed", map[string]interface{}{
			"user_id":  id,
			"category": gdprlog.SensitiveLog, // Password changes are highly sensitive
		})
	} else {
		// Fallback to standard logging
		log.Info().
			Int64("user_id", id).
			Msg("User password changed")
	}

	return nil
}

// ExistsByUsername checks if a user with the given username exists.
// The comparison is case-insensitive for better user experience.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - username: The username to check
//
// Returns:
//   - true if a user with the username exists
//   - false if no user with the username exists
//   - An error if the check fails
func (r *PostgresUserRepository) ExistsByUsername(ctx context.Context, username string) (bool, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query for PostgreSQL
	query := `SELECT EXISTS(SELECT 1 FROM users WHERE LOWER(username) = LOWER($1))`

	// Execute the query
	var exists bool
	err := r.db.QueryRowContext(ctx, query, username).Scan(&exists)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{username},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return false, fmt.Errorf("failed to check if username exists: %w", err)
	}

	return exists, nil
}

// ExistsByEmail checks if a user with the given email exists.
// The comparison is case-insensitive for better user experience.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - email: The email to check
//
// Returns:
//   - true if a user with the email exists
//   - false if no user with the email exists
//   - An error if the check fails
//
// For privacy reasons, this method avoids logging the actual email address.
func (r *PostgresUserRepository) ExistsByEmail(ctx context.Context, email string) (bool, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query for PostgreSQL
	query := `SELECT EXISTS(SELECT 1 FROM users WHERE LOWER(email) = LOWER($1))`

	// Execute the query
	var exists bool
	err := r.db.QueryRowContext(ctx, query, email).Scan(&exists)

	// Log the query execution with email redacted for GDPR compliance
	utils.LogDBQuery(
		query,
		[]interface{}{"[EMAIL-REDACTED]"}, // Don't log actual email in query parameters
		time.Since(startTime),
		err,
	)

	if err != nil {
		return false, fmt.Errorf("failed to check if email exists: %w", err)
	}

	return exists, nil
}
