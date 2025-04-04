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

// PatternRepository defines methods for interacting with search patterns
type PatternRepository interface {
	Create(ctx context.Context, pattern *models.SearchPattern) error
	GetByID(ctx context.Context, id int64) (*models.SearchPattern, error)
	GetBySettingID(ctx context.Context, settingID int64) ([]*models.SearchPattern, error)
	Update(ctx context.Context, pattern *models.SearchPattern) error
	Delete(ctx context.Context, id int64) error
	DeleteBySettingID(ctx context.Context, settingID int64) error
}

// PostgresPatternRepository is a PostgreSQL implementation of PatternRepository
type PostgresPatternRepository struct {
	db *database.Pool
}

// NewPatternRepository creates a new PatternRepository
func NewPatternRepository(db *database.Pool) PatternRepository {
	return &PostgresPatternRepository{
		db: db,
	}
}

// Create adds a new search pattern to the database
func (r *PostgresPatternRepository) Create(ctx context.Context, pattern *models.SearchPattern) error {
	// Start query timer
	startTime := time.Now()

	// Define the query with RETURNING for PostgreSQL
	query := `
		INSERT INTO search_patterns (setting_id, pattern_type, pattern_text)
		VALUES ($1, $2, $3)
		RETURNING pattern_id
	`

	// Execute the query
	err := r.db.QueryRowContext(
		ctx,
		query,
		pattern.SettingID,
		pattern.PatternType,
		pattern.PatternText,
	).Scan(&pattern.ID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{pattern.SettingID, pattern.PatternType, pattern.PatternText},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to create search pattern: %w", err)
	}

	log.Info().
		Int64("pattern_id", pattern.ID).
		Int64("setting_id", pattern.SettingID).
		Str("pattern_type", string(pattern.PatternType)).
		Msg("Search pattern created")

	return nil
}

// GetByID retrieves a search pattern by ID
func (r *PostgresPatternRepository) GetByID(ctx context.Context, id int64) (*models.SearchPattern, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT pattern_id, setting_id, pattern_type, pattern_text
		FROM search_patterns
		WHERE pattern_id = $1
	`

	// Execute the query
	pattern := &models.SearchPattern{}
	var patternType string
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&pattern.ID,
		&pattern.SettingID,
		&patternType,
		&pattern.PatternText,
	)

	// Convert string to PatternType
	pattern.PatternType = models.PatternType(patternType)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{id},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewNotFoundError("SearchPattern", id)
		}
		return nil, fmt.Errorf("failed to get search pattern by ID: %w", err)
	}

	return pattern, nil
}

// GetBySettingID retrieves all search patterns for a setting
func (r *PostgresPatternRepository) GetBySettingID(ctx context.Context, settingID int64) ([]*models.SearchPattern, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT pattern_id, setting_id, pattern_type, pattern_text
		FROM search_patterns
		WHERE setting_id = $1
		ORDER BY pattern_id
	`

	// Execute the query
	rows, err := r.db.QueryContext(ctx, query, settingID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{settingID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get search patterns by setting ID: %w", err)
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	// Parse the results
	var patterns []*models.SearchPattern
	for rows.Next() {
		pattern := &models.SearchPattern{}
		var patternType string
		if err := rows.Scan(
			&pattern.ID,
			&pattern.SettingID,
			&patternType,
			&pattern.PatternText,
		); err != nil {
			return nil, fmt.Errorf("failed to scan search pattern row: %w", err)
		}
		pattern.PatternType = models.PatternType(patternType)
		patterns = append(patterns, pattern)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating search pattern rows: %w", err)
	}

	return patterns, nil
}

// Update updates a search pattern in the database
func (r *PostgresPatternRepository) Update(ctx context.Context, pattern *models.SearchPattern) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		UPDATE search_patterns
		SET pattern_type = $1, pattern_text = $2
		WHERE pattern_id = $3
	`

	// Execute the query
	result, err := r.db.ExecContext(
		ctx,
		query,
		pattern.PatternType,
		pattern.PatternText,
		pattern.ID,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{pattern.PatternType, pattern.PatternText, pattern.ID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to update search pattern: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("SearchPattern", pattern.ID)
	}

	log.Info().
		Int64("pattern_id", pattern.ID).
		Str("pattern_type", string(pattern.PatternType)).
		Msg("Search pattern updated")

	return nil
}

// Delete removes a search pattern from the database
func (r *PostgresPatternRepository) Delete(ctx context.Context, id int64) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM search_patterns WHERE pattern_id = $1`

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
		return fmt.Errorf("failed to delete search pattern: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("SearchPattern", id)
	}

	log.Info().
		Int64("pattern_id", id).
		Msg("Search pattern deleted")

	return nil
}

// DeleteBySettingID removes all search patterns for a setting
func (r *PostgresPatternRepository) DeleteBySettingID(ctx context.Context, settingID int64) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM search_patterns WHERE setting_id = $1`

	// Execute the query
	result, err := r.db.ExecContext(ctx, query, settingID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{settingID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to delete search patterns by setting ID: %w", err)
	}

	// Log the deletion
	rowsAffected, _ := result.RowsAffected()
	log.Info().
		Int64("setting_id", settingID).
		Int64("count", rowsAffected).
		Msg("Search patterns deleted for setting")

	return nil
}
