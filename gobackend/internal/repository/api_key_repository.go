// Package repository provides data access interfaces and implementations for the HideMe application.
// It follows the repository pattern to abstract database operations and provide a clean API
// for data persistence operations.
//
// The package encapsulates all database interactions, enforcing proper data access patterns,
// transaction management, error handling, and security practices (including sensitive data redaction).
// All repositories use the database connection pool and follow consistent patterns for CRUD operations.
package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/lib/pq"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// APIKeyRepository defines methods for interacting with API keys in the database.
// It provides a clean interface for CRUD operations on API keys, allowing for
// authentication and authorization of external services interacting with the system.
type APIKeyRepository interface {
	// Create adds a new API key to the database.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - apiKey: The API key to store, with all required fields populated
	//
	// Returns:
	//   - An error if creation fails (e.g., due to duplicate key, database connectivity issues)
	//   - nil on successful creation
	Create(ctx context.Context, apiKey *models.APIKey) error

	// GetByID retrieves an API key by its unique identifier.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - id: The unique identifier of the API key
	//
	// Returns:
	//   - The API key if found
	//   - NotFoundError if the key doesn't exist
	//   - Other errors for database issues
	GetByID(ctx context.Context, id string) (*models.APIKey, error)

	// GetByUserID retrieves all API keys for a specific user.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - userID: The unique identifier of the user
	//
	// Returns:
	//   - A slice of API keys belonging to the user
	//   - An empty slice if no keys exist
	//   - An error if retrieval fails
	GetByUserID(ctx context.Context, userID int64) ([]*models.APIKey, error)

	// VerifyKey validates an API key by checking its ID and hash against the database.
	// This also verifies that the key has not expired.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - keyID: The unique identifier of the API key
	//   - keyHash: The hashed value of the API key
	//
	// Returns:
	//   - The API key if valid and not expired
	//   - InvalidTokenError if the key doesn't exist or hash doesn't match
	//   - ExpiredTokenError if the key exists but has expired
	//   - Other errors for database issues
	VerifyKey(ctx context.Context, keyID, keyHash string) (*models.APIKey, error)

	// Delete removes an API key from the database.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - id: The unique identifier of the API key to delete
	//
	// Returns:
	//   - NotFoundError if the key doesn't exist
	//   - Other errors for database issues
	Delete(ctx context.Context, id string) error

	// DeleteByUserID removes all API keys for a specific user.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - userID: The unique identifier of the user
	//
	// Returns:
	//   - An error if deletion fails
	//   - nil if deletion succeeds or there were no keys to delete
	DeleteByUserID(ctx context.Context, userID int64) error

	// DeleteExpired removes all expired API keys from the database.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//
	// Returns:
	//   - The number of expired keys deleted
	//   - An error if deletion fails
	DeleteExpired(ctx context.Context) (int64, error)

	GetAll(ctx context.Context) ([]*models.APIKey, error)
}

// PostgresAPIKeyRepository is a PostgreSQL implementation of APIKeyRepository.
// It implements all required methods using PostgreSQL-specific features
// and error handling.
type PostgresAPIKeyRepository struct {
	db *database.Pool
}

// NewAPIKeyRepository creates a new APIKeyRepository implementation for PostgreSQL.
//
// Parameters:
//   - db: A connection pool for PostgreSQL database access
//
// Returns:
//   - An implementation of the APIKeyRepository interface
func NewAPIKeyRepository(db *database.Pool) APIKeyRepository {
	return &PostgresAPIKeyRepository{
		db: db,
	}
}

// Create adds a new API key to the database.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - apiKey: The API key to store
//
// Returns:
//   - DuplicateError if an API key with the same ID already exists
//   - Other errors for database issues
func (r *PostgresAPIKeyRepository) Create(ctx context.Context, apiKey *models.APIKey) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		INSERT INTO api_keys (key_id, user_id, api_key_hash, name, expires_at, created_at)
		VALUES ($1, $2, $3, $4, $5, $6)
	`

	// Execute the query
	_, err := r.db.ExecContext(
		ctx,
		query,
		apiKey.ID,
		apiKey.UserID,
		apiKey.APIKeyHash,
		apiKey.Name,
		apiKey.ExpiresAt,
		apiKey.CreatedAt,
	)

	// Log the query execution with sensitive data redacted
	utils.LogDBQuery(
		query,
		[]interface{}{apiKey.ID, apiKey.UserID, constants.LogRedactedValue, apiKey.Name, apiKey.ExpiresAt, apiKey.CreatedAt},
		time.Since(startTime),
		err,
	)

	if err != nil {
		// Handle PostgreSQL specific errors
		if pqErr, ok := err.(*pq.Error); ok {
			// Check for duplicate key error
			if pqErr.Code == constants.PGErrorDuplicateConstraint {
				return utils.NewDuplicateError("APIKey", "id", apiKey.ID)
			}
		}
		return fmt.Errorf("failed to create API key: %w", err)
	}

	// Use the regular log function which now routes through GDPR logger
	log.Info().
		Str(constants.ParamKeyID, apiKey.ID).
		Int64(constants.ColumnUserID, apiKey.UserID).
		Str(constants.ColumnName, apiKey.Name).
		Time(constants.ColumnExpiresAt, apiKey.ExpiresAt).
		Msg(constants.LogEventAPIKey + " created")

	return nil
}

// GetByID retrieves an API key by ID.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - id: The unique identifier of the API key
//
// Returns:
//   - The API key if found
//   - NotFoundError if the key doesn't exist
//   - Other errors for database issues
func (r *PostgresAPIKeyRepository) GetByID(ctx context.Context, id string) (*models.APIKey, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT ` + constants.ColumnKeyID + `, ` + constants.ColumnUserID + `, ` + constants.ColumnAPIKeyHash + `, ` + constants.ColumnName + `, ` + constants.ColumnExpiresAt + `, ` + constants.ColumnCreatedAt + `
		FROM ` + constants.TableAPIKeys + `
		WHERE ` + constants.ColumnKeyID + ` = $1
	`

	// Execute the query
	apiKey := &models.APIKey{}
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&apiKey.ID,
		&apiKey.UserID,
		&apiKey.APIKeyHash,
		&apiKey.Name,
		&apiKey.ExpiresAt,
		&apiKey.CreatedAt,
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
			return nil, utils.NewNotFoundError("APIKey", id)
		}
		return nil, fmt.Errorf("failed to get API key by ID: %w", err)
	}

	return apiKey, nil
}

// GetByUserID retrieves all API keys for a user.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - userID: The unique identifier of the user
//
// Returns:
//   - A slice of API keys belonging to the user
//   - An empty slice if no keys exist
//   - An error if retrieval fails
func (r *PostgresAPIKeyRepository) GetByUserID(ctx context.Context, userID int64) ([]*models.APIKey, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT ` + constants.ColumnKeyID + `, ` + constants.ColumnUserID + `, ` + constants.ColumnAPIKeyHash + `, ` + constants.ColumnName + `, ` + constants.ColumnExpiresAt + `, ` + constants.ColumnCreatedAt + `
		FROM ` + constants.TableAPIKeys + `
		WHERE ` + constants.ColumnUserID + ` = $1
		ORDER BY ` + constants.ColumnCreatedAt + ` DESC
	`

	// Execute the query
	rows, err := r.db.QueryContext(ctx, query, userID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{userID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get API keys by user ID: %w", err)
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	// Parse the results
	var apiKeys []*models.APIKey
	for rows.Next() {
		apiKey := &models.APIKey{}
		err := rows.Scan(
			&apiKey.ID,
			&apiKey.UserID,
			&apiKey.APIKeyHash,
			&apiKey.Name,
			&apiKey.ExpiresAt,
			&apiKey.CreatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan API key row: %w", err)
		}
		apiKeys = append(apiKeys, apiKey)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating API key rows: %w", err)
	}

	return apiKeys, nil
}

// VerifyKey verifies an API key by its ID and hash.
// The key must exist, the hash must match, and the key must not be expired.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - keyID: The unique identifier of the API key
//   - keyHash: The hashed value of the API key
//
// Returns:
//   - The API key if valid and not expired
//   - InvalidTokenError if the key doesn't exist or hash doesn't match
//   - ExpiredTokenError if the key exists but has expired
//   - Other errors for database issues
func (r *PostgresAPIKeyRepository) VerifyKey(ctx context.Context, keyID, keyHash string) (*models.APIKey, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT ` + constants.ColumnKeyID + `, ` + constants.ColumnUserID + `, ` + constants.ColumnAPIKeyHash + `, ` + constants.ColumnName + `, ` + constants.ColumnExpiresAt + `, ` + constants.ColumnCreatedAt + `
		FROM ` + constants.TableAPIKeys + `
		WHERE ` + constants.ColumnKeyID + ` = $1 AND ` + constants.ColumnAPIKeyHash + ` = $2 AND ` + constants.ColumnExpiresAt + ` > $3
	`

	// Execute the query
	now := time.Now()
	apiKey := &models.APIKey{}
	err := r.db.QueryRowContext(ctx, query, keyID, keyHash, now).Scan(
		&apiKey.ID,
		&apiKey.UserID,
		&apiKey.APIKeyHash,
		&apiKey.Name,
		&apiKey.ExpiresAt,
		&apiKey.CreatedAt,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{keyID, constants.LogRedactedValue, now},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			// Check if the key exists but is expired
			expiredQuery := `SELECT ` + constants.ColumnExpiresAt + ` FROM ` + constants.TableAPIKeys + ` WHERE ` + constants.ColumnKeyID + ` = $1`
			var expiresAt time.Time
			expiredErr := r.db.QueryRowContext(ctx, expiredQuery, keyID).Scan(&expiresAt)

			if expiredErr == nil && expiresAt.Before(now) {
				return nil, utils.NewExpiredTokenError()
			}

			return nil, utils.NewInvalidTokenError()
		}
		return nil, fmt.Errorf("failed to verify API key: %w", err)
	}

	// Log the successful verification
	log.Info().
		Str(constants.ParamKeyID, apiKey.ID).
		Int64(constants.ColumnUserID, apiKey.UserID).
		Msg(constants.LogEventAPIKey + " verified")

	return apiKey, nil
}

// Delete removes an API key from the database.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - id: The unique identifier of the API key to delete
//
// Returns:
//   - NotFoundError if the key doesn't exist
//   - Other errors for database issues
func (r *PostgresAPIKeyRepository) Delete(ctx context.Context, id string) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM ` + constants.TableAPIKeys + ` WHERE ` + constants.ColumnKeyID + ` = $1`

	// Execute the query
	result, err := r.db.ExecContext(ctx, query, id)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{id},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to delete API key: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("APIKey", id)
	}

	log.Info().
		Str(constants.ParamKeyID, id).
		Msg(constants.LogEventAPIKey + " deleted")

	return nil
}

// DeleteByUserID removes all API keys for a user.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - userID: The unique identifier of the user
//
// Returns:
//   - An error if deletion fails
//   - nil if deletion succeeds or there were no keys to delete
func (r *PostgresAPIKeyRepository) DeleteByUserID(ctx context.Context, userID int64) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM ` + constants.TableAPIKeys + ` WHERE ` + constants.ColumnUserID + ` = $1`

	// Execute the query
	result, err := r.db.ExecContext(ctx, query, userID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{userID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to delete API keys by user ID: %w", err)
	}

	// Log the deletion
	rowsAffected, _ := result.RowsAffected()
	log.Info().
		Int64(constants.ColumnUserID, userID).
		Int64("count", rowsAffected).
		Msg(constants.LogEventAPIKey + " deleted for user")

	return nil
}

// DeleteExpired removes all expired API keys.
// This is typically used by a scheduled cleanup process.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//
// Returns:
//   - The number of expired keys deleted
//   - An error if deletion fails
func (r *PostgresAPIKeyRepository) DeleteExpired(ctx context.Context) (int64, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM ` + constants.TableAPIKeys + ` WHERE ` + constants.ColumnExpiresAt + ` < $1`

	// Execute the query
	now := time.Now()
	result, err := r.db.ExecContext(ctx, query, now)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{now},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return 0, fmt.Errorf("failed to delete expired API keys: %w", err)
	}

	// Log the deletion
	count, err := result.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("failed to get rows affected: %w", err)
	}

	log.Info().
		Int64("count", count).
		Msg("Expired API keys deleted")

	return count, nil
}

func (r *PostgresAPIKeyRepository) GetByHash(ctx context.Context, hash string) (*models.APIKey, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT ` + constants.ColumnKeyID + `, ` + constants.ColumnUserID + `, ` + constants.ColumnAPIKeyHash + `, ` + constants.ColumnName + `, ` + constants.ColumnExpiresAt + `, ` + constants.ColumnCreatedAt + `
        FROM ` + constants.TableAPIKeys + `
        WHERE ` + constants.ColumnAPIKeyHash + ` = $1 AND ` + constants.ColumnExpiresAt + ` > $2
    `

	// Execute the query
	now := time.Now()
	apiKey := &models.APIKey{}
	err := r.db.QueryRowContext(ctx, query, hash, now).Scan(
		&apiKey.ID,
		&apiKey.UserID,
		&apiKey.APIKeyHash,
		&apiKey.Name,
		&apiKey.ExpiresAt,
		&apiKey.CreatedAt,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{constants.LogRedactedValue, now},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewInvalidTokenError()
		}
		return nil, fmt.Errorf("failed to get API key by hash: %w", err)
	}

	return apiKey, nil
}

func (r *PostgresAPIKeyRepository) GetAll(ctx context.Context) ([]*models.APIKey, error) {
	startTime := time.Now()

	query := `
		SELECT key_id, user_id, api_key_hash, name, expires_at, created_at
		FROM api_keys
	`

	rows, err := r.db.QueryContext(ctx, query)

	utils.LogDBQuery(
		query,
		nil,
		time.Since(startTime),
		err,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get API keys: %w", err)
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	var apiKeys []*models.APIKey
	for rows.Next() {
		apiKey := &models.APIKey{}
		err := rows.Scan(
			&apiKey.ID,
			&apiKey.UserID,
			&apiKey.APIKeyHash,
			&apiKey.Name,
			&apiKey.ExpiresAt,
			&apiKey.CreatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan API key row: %w", err)
		}
		apiKeys = append(apiKeys, apiKey)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating API key rows: %w", err)
	}

	return apiKeys, nil
}
