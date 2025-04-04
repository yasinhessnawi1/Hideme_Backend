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

// SettingsRepository defines methods for interacting with user settings
type SettingsRepository interface {
	Create(ctx context.Context, settings *models.UserSetting) error
	GetByUserID(ctx context.Context, userID int64) (*models.UserSetting, error)
	Update(ctx context.Context, settings *models.UserSetting) error
	Delete(ctx context.Context, id int64) error
	DeleteByUserID(ctx context.Context, userID int64) error
	EnsureDefaultSettings(ctx context.Context, userID int64) (*models.UserSetting, error)
}

// PostgresSettingsRepository is a PostgreSQL implementation of SettingsRepository
type PostgresSettingsRepository struct {
	db *database.Pool
}

// NewSettingsRepository creates a new SettingsRepository
func NewSettingsRepository(db *database.Pool) SettingsRepository {
	return &PostgresSettingsRepository{
		db: db,
	}
}

// Create adds new user settings to the database
func (r *PostgresSettingsRepository) Create(ctx context.Context, settings *models.UserSetting) error {
	// Start query timer
	startTime := time.Now()

	// Set created/updated timestamps
	now := time.Now()
	settings.CreatedAt = now
	settings.UpdatedAt = now

	// Define the query with RETURNING for PostgreSQL
	query := `
		INSERT INTO user_settings (user_id, remove_images, created_at, updated_at)
		VALUES ($1, $2, $3, $4)
		RETURNING setting_id
	`

	// Execute the query
	err := r.db.QueryRowContext(
		ctx,
		query,
		settings.UserID,
		settings.RemoveImages,
		settings.CreatedAt,
		settings.UpdatedAt,
	).Scan(&settings.ID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{settings.UserID, settings.RemoveImages, settings.CreatedAt, settings.UpdatedAt},
		time.Since(startTime),
		err,
	)

	if err != nil {
		// Check for unique constraint violations
		if pqErr, ok := err.(*pq.Error); ok {
			// 23505 is the PostgreSQL error code for unique_violation
			if pqErr.Code == "23505" {
				if pqErr.Constraint == "idx_user_id" || pqErr.Constraint == "user_settings_user_id_key" {
					return utils.NewDuplicateError("UserSetting", "user_id", settings.UserID)
				}
			}
		}
		return fmt.Errorf("failed to create user settings: %w", err)
	}

	log.Info().
		Int64("setting_id", settings.ID).
		Int64("user_id", settings.UserID).
		Bool("remove_images", settings.RemoveImages).
		Msg("User settings created")

	return nil
}

// GetByUserID retrieves user settings by user ID
func (r *PostgresSettingsRepository) GetByUserID(ctx context.Context, userID int64) (*models.UserSetting, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT setting_id, user_id, remove_images, created_at, updated_at
		FROM user_settings
		WHERE user_id = $1
	`

	// Execute the query
	settings := &models.UserSetting{}
	err := r.db.QueryRowContext(ctx, query, userID).Scan(
		&settings.ID,
		&settings.UserID,
		&settings.RemoveImages,
		&settings.CreatedAt,
		&settings.UpdatedAt,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{userID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewNotFoundError("UserSetting", fmt.Sprintf("user_id=%d", userID))
		}
		return nil, fmt.Errorf("failed to get user settings by user ID: %w", err)
	}

	return settings, nil
}

// Update updates user settings in the database
func (r *PostgresSettingsRepository) Update(ctx context.Context, settings *models.UserSetting) error {
	// Start query timer
	startTime := time.Now()

	// Update the updated_at timestamp
	settings.UpdatedAt = time.Now()

	// Define the query
	query := `
		UPDATE user_settings
		SET remove_images = $1, updated_at = $2
		WHERE setting_id = $3
	`

	// Execute the query
	result, err := r.db.ExecContext(
		ctx,
		query,
		settings.RemoveImages,
		settings.UpdatedAt,
		settings.ID,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{settings.RemoveImages, settings.UpdatedAt, settings.ID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to update user settings: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("UserSetting", settings.ID)
	}

	log.Info().
		Int64("setting_id", settings.ID).
		Int64("user_id", settings.UserID).
		Bool("remove_images", settings.RemoveImages).
		Msg("User settings updated")

	return nil
}

// Delete removes user settings from the database
func (r *PostgresSettingsRepository) Delete(ctx context.Context, id int64) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM user_settings WHERE setting_id = $1`

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
		return fmt.Errorf("failed to delete user settings: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("UserSetting", id)
	}

	log.Info().
		Int64("setting_id", id).
		Msg("User settings deleted")

	return nil
}

// DeleteByUserID removes user settings for a specific user
func (r *PostgresSettingsRepository) DeleteByUserID(ctx context.Context, userID int64) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM user_settings WHERE user_id = $1`

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
		return fmt.Errorf("failed to delete user settings by user ID: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("UserSetting", fmt.Sprintf("user_id=%d", userID))
	}

	log.Info().
		Int64("user_id", userID).
		Msg("User settings deleted by user ID")

	return nil
}

// EnsureDefaultSettings ensures that default settings exist for a user, creating them if necessary
func (r *PostgresSettingsRepository) EnsureDefaultSettings(ctx context.Context, userID int64) (*models.UserSetting, error) {
	// Try to get existing settings
	settings, err := r.GetByUserID(ctx, userID)
	if err != nil {
		// If settings don't exist, create them
		if utils.IsNotFoundError(err) {
			settings = models.NewUserSetting(userID)
			if err := r.Create(ctx, settings); err != nil {
				return nil, fmt.Errorf("failed to create default settings: %w", err)
			}
			return settings, nil
		}
		// If it's a different error, return it
		return nil, err
	}

	// Settings already exist
	return settings, nil
}
