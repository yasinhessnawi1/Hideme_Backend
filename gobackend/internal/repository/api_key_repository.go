package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/lib/pq"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// APIKeyRepository defines methods for interacting with API keys
type APIKeyRepository interface {
	Create(ctx context.Context, apiKey *models.APIKey) error
	GetByID(ctx context.Context, id string) (*models.APIKey, error)
	GetByUserID(ctx context.Context, userID int64) ([]*models.APIKey, error)
	VerifyKey(ctx context.Context, keyID, keyHash string) (*models.APIKey, error)
	Delete(ctx context.Context, id string) error
	DeleteByUserID(ctx context.Context, userID int64) error
	DeleteExpired(ctx context.Context) (int64, error)
}

// PostgresAPIKeyRepository is a PostgreSQL implementation of APIKeyRepository
type PostgresAPIKeyRepository struct {
	db *database.Pool
}

// NewAPIKeyRepository creates a new APIKeyRepository
func NewAPIKeyRepository(db *database.Pool) APIKeyRepository {
	return &PostgresAPIKeyRepository{
		db: db,
	}
}

// Create adds a new API key to the database
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

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{apiKey.ID, apiKey.UserID, "[REDACTED]", apiKey.Name, apiKey.ExpiresAt, apiKey.CreatedAt},
		time.Since(startTime),
		err,
	)

	if err != nil {
		// Handle PostgreSQL specific errors
		if pqErr, ok := err.(*pq.Error); ok {
			// 23505 is the PostgreSQL error code for unique_violation
			if pqErr.Code == "23505" {
				return utils.NewDuplicateError("APIKey", "id", apiKey.ID)
			}
		}
		return fmt.Errorf("failed to create API key: %w", err)
	}

	log.Info().
		Str("key_id", apiKey.ID).
		Int64("user_id", apiKey.UserID).
		Str("name", apiKey.Name).
		Time("expires_at", apiKey.ExpiresAt).
		Msg("API key created")

	return nil
}

// GetByID retrieves an API key by ID
func (r *PostgresAPIKeyRepository) GetByID(ctx context.Context, id string) (*models.APIKey, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT key_id, user_id, api_key_hash, name, expires_at, created_at
		FROM api_keys
		WHERE key_id = $1
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

// GetByUserID retrieves all API keys for a user
func (r *PostgresAPIKeyRepository) GetByUserID(ctx context.Context, userID int64) ([]*models.APIKey, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT key_id, user_id, api_key_hash, name, expires_at, created_at
		FROM api_keys
		WHERE user_id = $1
		ORDER BY created_at DESC
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

// VerifyKey verifies an API key by its ID and hash
func (r *PostgresAPIKeyRepository) VerifyKey(ctx context.Context, keyID, keyHash string) (*models.APIKey, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT key_id, user_id, api_key_hash, name, expires_at, created_at
		FROM api_keys
		WHERE key_id = $1 AND api_key_hash = $2 AND expires_at > $3
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
		[]interface{}{keyID, "[REDACTED]", now},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			// Check if the key exists but is expired
			expiredQuery := `SELECT expires_at FROM api_keys WHERE key_id = $1`
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
		Str("key_id", apiKey.ID).
		Int64("user_id", apiKey.UserID).
		Msg("API key verified")

	return apiKey, nil
}

// Delete removes an API key from the database
func (r *PostgresAPIKeyRepository) Delete(ctx context.Context, id string) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM api_keys WHERE key_id = $1`

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
		Str("key_id", id).
		Msg("API key deleted")

	return nil
}

// DeleteByUserID removes all API keys for a user
func (r *PostgresAPIKeyRepository) DeleteByUserID(ctx context.Context, userID int64) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM api_keys WHERE user_id = $1`

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
		Int64("user_id", userID).
		Int64("count", rowsAffected).
		Msg("API keys deleted for user")

	return nil
}

// DeleteExpired removes all expired API keys
func (r *PostgresAPIKeyRepository) DeleteExpired(ctx context.Context) (int64, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM api_keys WHERE expires_at < $1`

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
