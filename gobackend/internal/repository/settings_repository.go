// Package repository provides data access interfaces and implementations for the HideMe application.
// It follows the repository pattern to abstract database operations and provide a clean API
// for data persistence operations.
//
// This file implements the settings repository, which manages user-specific configuration options
// for document processing and application behavior. These settings control features like
// detection thresholds, ban list usage, and UI preferences.
package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// SettingsRepository defines methods for interacting with user settings in the database.
// It provides operations for managing configuration options that control the behavior
// of document processing and the application UI for each user.
type SettingsRepository interface {
	// Create adds new user settings to the database.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - settings: The user settings to store, with required fields populated
	//
	// Returns:
	//   - DuplicateError if settings already exist for the user
	//   - Other errors for database issues
	//   - nil on successful creation
	//
	// The settings ID will be populated after successful creation.
	Create(ctx context.Context, settings *models.UserSetting) error

	// GetByUserID retrieves user settings by user ID.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - userID: The unique identifier of the user
	//
	// Returns:
	//   - The user settings if found
	//   - NotFoundError if no settings exist for the user
	//   - Other errors for database issues
	GetByUserID(ctx context.Context, userID int64) (*models.UserSetting, error)

	// Update updates user settings in the database.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - settings: The user settings to update
	//
	// Returns:
	//   - NotFoundError if the settings don't exist
	//   - Other errors for database issues
	//   - nil on successful update
	//
	// This method automatically updates the UpdatedAt timestamp.
	Update(ctx context.Context, settings *models.UserSetting) error

	// Delete removes user settings from the database.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - id: The unique identifier of the settings to delete
	//
	// Returns:
	//   - NotFoundError if the settings don't exist
	//   - Other errors for database issues
	//   - nil on successful deletion
	Delete(ctx context.Context, id int64) error

	// DeleteByUserID removes user settings for a specific user.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - userID: The unique identifier of the user
	//
	// Returns:
	//   - NotFoundError if no settings exist for the user
	//   - Other errors for database issues
	//   - nil on successful deletion
	DeleteByUserID(ctx context.Context, userID int64) error

	// EnsureDefaultSettings ensures that default settings exist for a user,
	// creating them if necessary.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - userID: The unique identifier of the user
	//
	// Returns:
	//   - The user settings (either existing or newly created)
	//   - An error if retrieval or creation fails
	EnsureDefaultSettings(ctx context.Context, userID int64) (*models.UserSetting, error)
}

// PostgresSettingsRepository is a PostgreSQL implementation of SettingsRepository.
// It implements all required methods using PostgreSQL-specific features
// and error handling.
type PostgresSettingsRepository struct {
	db *database.Pool
}

// NewSettingsRepository creates a new SettingsRepository implementation for PostgreSQL.
//
// Parameters:
//   - db: A connection pool for PostgreSQL database access
//
// Returns:
//   - An implementation of the SettingsRepository interface
func NewSettingsRepository(db *database.Pool) SettingsRepository {
	return &PostgresSettingsRepository{
		db: db,
	}
}

// Create adds new user settings to the database.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - settings: The user settings to store
//
// Returns:
//   - DuplicateError if settings already exist for the user
//   - Other errors for database issues
//   - nil on successful creation
//
// The settings ID will be populated after successful creation.
func (r *PostgresSettingsRepository) Create(ctx context.Context, settings *models.UserSetting) error {
	// Start query timer
	startTime := time.Now()

	// Set created/updated timestamps
	now := time.Now()
	settings.CreatedAt = now
	settings.UpdatedAt = now

	// Define the query with RETURNING for PostgreSQL
	query := `
        INSERT INTO user_settings (user_id, remove_images, theme, detection_threshold, use_banlist_for_detection, auto_processing, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING setting_id
    `

	// Execute the query
	err := r.db.QueryRowContext(
		ctx,
		query,
		settings.UserID,
		settings.RemoveImages,
		settings.Theme,
		settings.DetectionThreshold,
		settings.UseBanlistForDetection,
		settings.AutoProcessing,
		settings.CreatedAt,
		settings.UpdatedAt,
	).Scan(&settings.ID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{settings.UserID, settings.RemoveImages, settings.Theme, settings.DetectionThreshold, settings.UseBanlistForDetection, settings.AutoProcessing, settings.CreatedAt, settings.UpdatedAt},
		time.Since(startTime),
		err,
	)

	if err != nil {
		// Check for unique constraint violations
		if utils.IsDuplicateKeyError(err) {
			return utils.NewDuplicateError("UserSetting", "user_id", settings.UserID)
		}
		return fmt.Errorf("failed to create user settings: %w", err)
	}

	log.Info().
		Int64("setting_id", settings.ID).
		Int64("user_id", settings.UserID).
		Bool("remove_images", settings.RemoveImages).
		Str("theme", settings.Theme).
		Bool("auto_processing", settings.AutoProcessing).
		Msg("User settings created")

	return nil
}

// GetByUserID retrieves user settings by user ID.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - userID: The unique identifier of the user
//
// Returns:
//   - The user settings if found
//   - NotFoundError if no settings exist for the user
//   - Other errors for database issues
func (r *PostgresSettingsRepository) GetByUserID(ctx context.Context, userID int64) (*models.UserSetting, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT setting_id, user_id, remove_images, theme, detection_threshold, use_banlist_for_detection, auto_processing, created_at, updated_at
        FROM user_settings
        WHERE user_id = $1
    `

	// Execute the query
	settings := &models.UserSetting{}
	err := r.db.QueryRowContext(ctx, query, userID).Scan(
		&settings.ID,
		&settings.UserID,
		&settings.RemoveImages,
		&settings.Theme,
		&settings.DetectionThreshold,
		&settings.UseBanlistForDetection,
		&settings.AutoProcessing,
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

// Update updates user settings in the database.
// This method automatically updates the UpdatedAt timestamp.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - settings: The user settings to update
//
// Returns:
//   - NotFoundError if the settings don't exist
//   - Other errors for database issues
//   - nil on successful update
func (r *PostgresSettingsRepository) Update(ctx context.Context, settings *models.UserSetting) error {
	// Start query timer
	startTime := time.Now()

	// Update the updated_at timestamp
	settings.UpdatedAt = time.Now()

	// Define the query
	query := `
        UPDATE user_settings
        SET remove_images = $1, theme = $2, detection_threshold = $3, use_banlist_for_detection = $4, auto_processing = $5, updated_at = $6
        WHERE setting_id = $7
    `

	// Execute the query
	result, err := r.db.ExecContext(
		ctx,
		query,
		settings.RemoveImages,
		settings.Theme,
		settings.DetectionThreshold,
		settings.UseBanlistForDetection,
		settings.AutoProcessing,
		settings.UpdatedAt,
		settings.ID,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{settings.RemoveImages, settings.Theme, settings.AutoProcessing, settings.UpdatedAt, settings.ID},
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
		Str("theme", settings.Theme).
		Bool("auto_processing", settings.AutoProcessing).
		Msg("User settings updated")

	return nil
}

// Delete removes user settings from the database.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - id: The unique identifier of the settings to delete
//
// Returns:
//   - NotFoundError if the settings don't exist
//   - Other errors for database issues
//   - nil on successful deletion
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

// DeleteByUserID removes user settings for a specific user.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - userID: The unique identifier of the user
//
// Returns:
//   - NotFoundError if no settings exist for the user
//   - Other errors for database issues
//   - nil on successful deletion
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

// EnsureDefaultSettings ensures that default settings exist for a user,
// creating them if necessary.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - userID: The unique identifier of the user
//
// Returns:
//   - The user settings (either existing or newly created)
//   - An error if retrieval or creation fails
//
// This method is idempotent and is designed to be called at the beginning of operations
// that require user settings to exist.
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
