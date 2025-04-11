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

// PostgresUserRepository is a PostgreSQL implementation of UserRepository
type PostgresUserRepository struct {
	db *database.Pool
}

// NewUserRepository creates a new UserRepository
func NewUserRepository(db *database.Pool) UserRepository {
	return &PostgresUserRepository{
		db: db,
	}
}

// Create adds a new user to the database
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

	// Log the query execution
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

	log.Info().
		Int64("user_id", user.ID).
		Str("username", user.Username).
		Str("email", user.Email).
		Msg("User created")

	return nil
}

// GetByID retrieves a user by ID
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

// GetByUsername retrieves a user by username
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

// GetByEmail retrieves a user by email
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

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{user.Username, user.Email, user.UpdatedAt, user.ID},
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
					return utils.NewDuplicateError("User", "email", user.Email)
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

	log.Info().
		Int64("user_id", user.ID).
		Str("username", user.Username).
		Str("email", user.Email).
		Msg("User updated")

	return nil
}

// Delete removes a user from the database
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

		log.Info().
			Int64("user_id", id).
			Msg("User deleted")

		return nil
	})
}

// ChangePassword updates a user's password
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

	log.Info().
		Int64("user_id", id).
		Msg("User password changed")

	return nil
}

// ExistsByUsername checks if a user with the given username exists
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

// ExistsByEmail checks if a user with the given email exists
func (r *PostgresUserRepository) ExistsByEmail(ctx context.Context, email string) (bool, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query for PostgreSQL
	query := `SELECT EXISTS(SELECT 1 FROM users WHERE LOWER(email) = LOWER($1))`

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
