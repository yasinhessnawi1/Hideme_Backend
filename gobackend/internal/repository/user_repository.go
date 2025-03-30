// internal/repository/user_repository.go
package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// UserRepository defines methods for interacting with user data
type UserRepository interface {
	Create(ctx context.Context, user *models.User) error
	GetByID(ctx context.Context, id int64) (*models.User, error)
	GetByUsername(ctx context.Context, username string) (*models.User, error)
	GetByEmail(ctx context.Context, email string) (*models.User, error)
	Update(ctx context.Context, user *models.User) error
	Delete(ctx context.Context, id int64) error
	ChangePassword(ctx context.Context, id int64, passwordHash, salt string) error
	ExistsByUsername(ctx context.Context, username string) (bool, error)
	ExistsByEmail(ctx context.Context, email string) (bool, error)
}

// MysqlUserRepository is a MySQL implementation of UserRepository
type MysqlUserRepository struct {
	db *database.Pool
}

// NewUserRepository creates a new UserRepository
func NewUserRepository(db *database.Pool) UserRepository {
	return &MysqlUserRepository{
		db: db,
	}
}

// Create adds a new user to the database
func (r *MysqlUserRepository) Create(ctx context.Context, user *models.User) error {
	// Start query timer
	startTime := time.Now()

	// Set created/updated timestamps
	now := time.Now()
	user.CreatedAt = now
	user.UpdatedAt = now

	// Define the query
	query := `
        INSERT INTO users (username, email, password_hash, salt, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    `

	// Execute the query
	result, err := r.db.ExecContext(
		ctx,
		query,
		user.Username,
		user.Email,
		user.PasswordHash,
		user.Salt,
		user.CreatedAt,
		user.UpdatedAt,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{user.Username, user.Email, "[REDACTED]", "[REDACTED]", user.CreatedAt, user.UpdatedAt},
		time.Since(startTime),
		err,
	)

	if err != nil {
		// Check for unique constraint violations
		if utils.IsDuplicateKeyError(err) {
			if utils.IsUniqueViolation(err, "users_username_key") {
				return utils.NewDuplicateError("User", "username", user.Username)
			}
			if utils.IsUniqueViolation(err, "users_email_key") {
				return utils.NewDuplicateError("User", "email", user.Email)
			}
		}
		return fmt.Errorf("failed to create user: %w", err)
	}

	// Get the last insert ID
	userID, err := result.LastInsertId()
	if err != nil {
		return fmt.Errorf("failed to get user ID: %w", err)
	}

	// Set the user ID
	user.ID = userID

	log.Info().
		Int64("user_id", userID).
		Str("username", user.Username).
		Str("email", user.Email).
		Msg("User created")

	return nil
}

// GetByID retrieves a user by ID
func (r *MysqlUserRepository) GetByID(ctx context.Context, id int64) (*models.User, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT user_id, username, email, password_hash, salt, created_at, updated_at
        FROM users
        WHERE user_id = ?
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

// GetByUsername retrieves a user by username
func (r *MysqlUserRepository) GetByUsername(ctx context.Context, username string) (*models.User, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query with case-insensitive comparison
	query := `
        SELECT user_id, username, email, password_hash, salt, created_at, updated_at
        FROM users
        WHERE LOWER(username) = LOWER(?)
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

// GetByEmail retrieves a user by email
func (r *MysqlUserRepository) GetByEmail(ctx context.Context, email string) (*models.User, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query with case-insensitive comparison
	query := `
        SELECT user_id, username, email, password_hash, salt, created_at, updated_at
        FROM users
        WHERE LOWER(email) = LOWER(?)
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

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{email},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewNotFoundError("User", fmt.Sprintf("email=%s", email))
		}
		return nil, fmt.Errorf("failed to get user by email: %w", err)
	}

	return user, nil
}

// Update updates a user in the database
func (r *MysqlUserRepository) Update(ctx context.Context, user *models.User) error {
	// Start query timer
	startTime := time.Now()

	// Update the updated_at timestamp
	user.UpdatedAt = time.Now()

	// Define the query
	query := `
        UPDATE users
        SET username = ?, email = ?, updated_at = ?
        WHERE user_id = ?
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

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{user.Username, user.Email, user.UpdatedAt, user.ID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		// Check for unique constraint violations
		if utils.IsDuplicateKeyError(err) {
			if strings.Contains(err.Error(), "username") {
				return utils.NewDuplicateError("User", "username", user.Username)
			}
			if strings.Contains(err.Error(), "email") {
				return utils.NewDuplicateError("User", "email", user.Email)
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

	log.Info().
		Int64("user_id", user.ID).
		Str("username", user.Username).
		Str("email", user.Email).
		Msg("User updated")

	return nil
}

// Delete removes a user from the database
func (r *MysqlUserRepository) Delete(ctx context.Context, id int64) error {
	// Start query timer
	startTime := time.Now()

	// Execute the delete within a transaction to cascade properly
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// Delete related records first (this would be handled by foreign key cascades)

		// Finally, delete the user
		query := "DELETE FROM users WHERE user_id = ?"
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

		log.Info().
			Int64("user_id", id).
			Msg("User deleted")

		return nil
	})
}

// ChangePassword updates a user's password
func (r *MysqlUserRepository) ChangePassword(ctx context.Context, id int64, passwordHash, salt string) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        UPDATE users
        SET password_hash = ?, salt = ?, updated_at = ?
        WHERE user_id = ?
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

	log.Info().
		Int64("user_id", id).
		Msg("User password changed")

	return nil
}

// ExistsByUsername checks if a user with the given username exists
func (r *MysqlUserRepository) ExistsByUsername(ctx context.Context, username string) (bool, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `SELECT EXISTS(SELECT 1 FROM users WHERE LOWER(username) = LOWER(?))`

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

// ExistsByEmail checks if a user with the given email exists
func (r *MysqlUserRepository) ExistsByEmail(ctx context.Context, email string) (bool, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `SELECT EXISTS(SELECT 1 FROM users WHERE LOWER(email) = LOWER(?))`

	// Execute the query
	var exists bool
	err := r.db.QueryRowContext(ctx, query, email).Scan(&exists)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{email},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return false, fmt.Errorf("failed to check if email exists: %w", err)
	}

	return exists, nil
}
