// Package repository provides data access interfaces and implementations for the HideMe application.
// It follows the repository pattern to abstract database operations and provide a clean API
// for data persistence operations.
//
// This file implements the ban list repository, which manages collections of words that should be
// excluded from sensitive information detection. Ban lists help reduce false positives by explicitly
// marking certain terms as non-sensitive in a user's context.
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

// BanListRepository defines methods for interacting with ban lists in the database.
// It provides operations for managing lists of words that should be excluded from
// sensitive information detection, helping to customize detection algorithms
// for each user's specific needs.
type BanListRepository interface {
	// GetByID retrieves a ban list by its unique identifier.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - id: The unique identifier of the ban list
	//
	// Returns:
	//   - The ban list if found
	//   - NotFoundError if the ban list doesn't exist
	//   - Other errors for database issues
	GetByID(ctx context.Context, id int64) (*models.BanList, error)

	// GetBySettingID retrieves a ban list associated with specific user settings.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - settingID: The ID of the user settings
	//
	// Returns:
	//   - The ban list if found
	//   - NotFoundError if no ban list exists for the settings
	//   - Other errors for database issues
	GetBySettingID(ctx context.Context, settingID int64) (*models.BanList, error)

	// CreateBanList creates a new ban list for specific user settings.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - settingID: The ID of the user settings to associate with the ban list
	//
	// Returns:
	//   - The newly created ban list
	//   - DuplicateError if a ban list already exists for the settings
	//   - Other errors for database issues
	CreateBanList(ctx context.Context, settingID int64) (*models.BanList, error)

	// Delete removes a ban list and all its words.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - id: The unique identifier of the ban list to delete
	//
	// Returns:
	//   - NotFoundError if the ban list doesn't exist
	//   - Other errors for database issues
	Delete(ctx context.Context, id int64) error

	// Ban list word operations

	// GetBanListWords retrieves all words in a ban list.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - banListID: The unique identifier of the ban list
	//
	// Returns:
	//   - A slice of words in the ban list
	//   - An empty slice if the ban list has no words
	//   - An error if retrieval fails
	GetBanListWords(ctx context.Context, banListID int64) ([]string, error)

	// AddWords adds words to a ban list.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - banListID: The unique identifier of the ban list
	//   - words: The words to add to the ban list
	//
	// Returns:
	//   - An error if addition fails
	//   - nil if addition succeeds or there were no words to add
	//
	// This method uses an upsert approach, so calling it with existing words
	// will not cause errors.
	AddWords(ctx context.Context, banListID int64, words []string) error

	// RemoveWords removes words from a ban list.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - banListID: The unique identifier of the ban list
	//   - words: The words to remove from the ban list
	//
	// Returns:
	//   - An error if removal fails
	//   - nil if removal succeeds or there were no words to remove
	//
	// This method is idempotent - removing words that don't exist is not an error.
	RemoveWords(ctx context.Context, banListID int64, words []string) error

	// WordExists checks if a word exists in a ban list.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - banListID: The unique identifier of the ban list
	//   - word: The word to check
	//
	// Returns:
	//   - true if the word exists in the ban list
	//   - false if the word does not exist in the ban list
	//   - An error if the check fails
	WordExists(ctx context.Context, banListID int64, word string) (bool, error)
}

// PostgresBanListRepository is a PostgreSQL implementation of BanListRepository.
// It implements all required methods using PostgreSQL-specific features
// and error handling.
type PostgresBanListRepository struct {
	db *database.Pool
}

// NewBanListRepository creates a new BanListRepository implementation for PostgreSQL.
//
// Parameters:
//   - db: A connection pool for PostgreSQL database access
//
// Returns:
//   - An implementation of the BanListRepository interface
func NewBanListRepository(db *database.Pool) BanListRepository {
	return &PostgresBanListRepository{
		db: db,
	}
}

// GetByID retrieves a ban list by ID.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - id: The unique identifier of the ban list
//
// Returns:
//   - The ban list if found
//   - NotFoundError if the ban list doesn't exist
//   - Other errors for database issues
func (r *PostgresBanListRepository) GetByID(ctx context.Context, id int64) (*models.BanList, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT ` + constants.ColumnBanID + `, ` + constants.ColumnSettingID + `
        FROM ` + constants.TableBanLists + `
        WHERE ` + constants.ColumnBanID + ` = $1
    `

	// Execute the query
	banList := &models.BanList{}
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&banList.ID,
		&banList.SettingID,
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
			return nil, utils.NewNotFoundError("BanList", id)
		}
		return nil, fmt.Errorf("failed to get ban list by ID: %w", err)
	}

	return banList, nil
}

// GetBySettingID retrieves a ban list by setting ID.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - settingID: The ID of the user settings
//
// Returns:
//   - The ban list if found
//   - NotFoundError if no ban list exists for the settings
//   - Other errors for database issues
func (r *PostgresBanListRepository) GetBySettingID(ctx context.Context, settingID int64) (*models.BanList, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT ` + constants.ColumnBanID + `, ` + constants.ColumnSettingID + `
        FROM ` + constants.TableBanLists + `
        WHERE ` + constants.ColumnSettingID + ` = $1
    `

	// Execute the query
	banList := &models.BanList{}
	err := r.db.QueryRowContext(ctx, query, settingID).Scan(
		&banList.ID,
		&banList.SettingID,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{settingID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewNotFoundError("BanList", fmt.Sprintf("setting_id=%d", settingID))
		}
		return nil, fmt.Errorf("failed to get ban list by setting ID: %w", err)
	}

	return banList, nil
}

// CreateBanList creates a new ban list for a setting.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - settingID: The ID of the user settings to associate with the ban list
//
// Returns:
//   - The newly created ban list
//   - DuplicateError if a ban list already exists for the settings
//   - Other errors for database issues
func (r *PostgresBanListRepository) CreateBanList(ctx context.Context, settingID int64) (*models.BanList, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        INSERT INTO ` + constants.TableBanLists + ` (` + constants.ColumnSettingID + `)
        VALUES ($1)
        RETURNING ` + constants.ColumnBanID + `
    `

	// Execute the query
	var banID int64
	err := r.db.QueryRowContext(ctx, query, settingID).Scan(&banID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{settingID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		// Check for unique constraint violations
		if pqErr, ok := err.(*pq.Error); ok {
			// Check for duplicate key error
			if pqErr.Code == constants.PGErrorDuplicateConstraint {
				return nil, utils.NewDuplicateError("BanList", constants.ColumnSettingID, settingID)
			}
		}
		return nil, fmt.Errorf("failed to create ban list: %w", err)
	}

	banList := &models.BanList{
		ID:        banID,
		SettingID: settingID,
	}

	log.Info().
		Int64(constants.ColumnBanID, banID).
		Int64(constants.ColumnSettingID, settingID).
		Msg("Ban list created")

	return banList, nil
}

// Delete removes a ban list and all its words.
// This operation uses a transaction to ensure both the ban list and its words are deleted atomically.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - id: The unique identifier of the ban list to delete
//
// Returns:
//   - NotFoundError if the ban list doesn't exist
//   - Other errors for database issues
func (r *PostgresBanListRepository) Delete(ctx context.Context, id int64) error {
	// Start query timer
	startTime := time.Now()

	// Execute delete within a transaction to cascade properly
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// First delete all words in the ban list
		wordQuery := "DELETE FROM " + constants.TableBanListWords + " WHERE " + constants.ColumnBanID + " = $1"
		_, err := tx.ExecContext(ctx, wordQuery, id)
		if err != nil {
			return fmt.Errorf("failed to delete ban list words: %w", err)
		}

		// Then delete the ban list itself
		listQuery := "DELETE FROM " + constants.TableBanLists + " WHERE " + constants.ColumnBanID + " = $1"
		result, err := tx.ExecContext(ctx, listQuery, id)

		// Log the query execution
		utils.LogDBQuery(
			listQuery,
			[]interface{}{id},
			time.Since(startTime),
			err,
		)

		if err != nil {
			return fmt.Errorf("failed to delete ban list: %w", err)
		}

		// Check if any rows were affected
		rowsAffected, err := result.RowsAffected()
		if err != nil {
			return fmt.Errorf("failed to get rows affected: %w", err)
		}

		if rowsAffected == 0 {
			return utils.NewNotFoundError("BanList", id)
		}

		log.Info().
			Int64(constants.ColumnBanID, id).
			Msg("Ban list deleted")

		return nil
	})
}

// GetBanListWords retrieves all words in a ban list.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - banListID: The unique identifier of the ban list
//
// Returns:
//   - A slice of words in the ban list
//   - An empty slice if the ban list has no words
//   - An error if retrieval fails
func (r *PostgresBanListRepository) GetBanListWords(ctx context.Context, banListID int64) ([]string, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT ` + constants.ColumnWord + `
        FROM ` + constants.TableBanListWords + `
        WHERE ` + constants.ColumnBanID + ` = $1
        ORDER BY ` + constants.ColumnWord + `
    `

	// Execute the query
	rows, err := r.db.QueryContext(ctx, query, banListID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{banListID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get ban list words: %w", err)
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	// Parse the results
	var words []string
	for rows.Next() {
		var word string
		if err := rows.Scan(&word); err != nil {
			return nil, fmt.Errorf("failed to scan ban list word: %w", err)
		}
		words = append(words, word)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating ban list words: %w", err)
	}

	return words, nil
}

// AddWords adds words to a ban list.
// This method uses a transaction to ensure atomicity and an upsert approach
// to handle duplicate words gracefully.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - banListID: The unique identifier of the ban list
//   - words: The words to add to the ban list
//
// Returns:
//   - An error if addition fails
//   - nil if addition succeeds or there were no words to add
func (r *PostgresBanListRepository) AddWords(ctx context.Context, banListID int64, words []string) error {
	if len(words) == 0 {
		return nil
	}

	// Start query timer
	startTime := time.Now()

	// Execute within a transaction
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// Define the query - PostgreSQL version uses ON CONFLICT for upsert
		query := `
            INSERT INTO ` + constants.TableBanListWords + ` (` + constants.ColumnBanID + `, ` + constants.ColumnWord + `)
            VALUES ($1, $2)
            ON CONFLICT (` + constants.ColumnBanID + `, ` + constants.ColumnWord + `) DO UPDATE SET ` + constants.ColumnWord + ` = EXCLUDED.` + constants.ColumnWord + `
        `

		// Insert each word individually
		for _, word := range words {
			_, err := tx.ExecContext(ctx, query, banListID, word)
			if err != nil {
				return fmt.Errorf("failed to add word to ban list: %w", err)
			}
		}

		// Log the operation
		utils.LogDBQuery(
			fmt.Sprintf("Added %d words to ban list", len(words)),
			[]interface{}{banListID},
			time.Since(startTime),
			nil,
		)

		log.Info().
			Int64(constants.ColumnBanID, banListID).
			Int("word_count", len(words)).
			Msg("Words added to ban list")

		return nil
	})
}

// RemoveWords removes words from a ban list.
// This method uses a transaction to ensure atomicity and is idempotent -
// removing words that don't exist is not an error.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - banListID: The unique identifier of the ban list
//   - words: The words to remove from the ban list
//
// Returns:
//   - An error if removal fails
//   - nil if removal succeeds or there were no words to remove
func (r *PostgresBanListRepository) RemoveWords(ctx context.Context, banListID int64, words []string) error {
	if len(words) == 0 {
		return nil
	}

	// Start query timer
	startTime := time.Now()

	// Execute within a transaction
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// Define the query
		query := `
            DELETE FROM ` + constants.TableBanListWords + `
            WHERE ` + constants.ColumnBanID + ` = $1 AND ` + constants.ColumnWord + ` = $2
        `

		// Delete each word individually
		for _, word := range words {
			_, err := tx.ExecContext(ctx, query, banListID, word)
			if err != nil {
				return fmt.Errorf("failed to remove word from ban list: %w", err)
			}
		}

		// Log the operation
		utils.LogDBQuery(
			fmt.Sprintf("Removed %d words from ban list", len(words)),
			[]interface{}{banListID},
			time.Since(startTime),
			nil,
		)

		log.Info().
			Int64(constants.ColumnBanID, banListID).
			Int("word_count", len(words)).
			Msg("Words removed from ban list")

		return nil
	})
}

// WordExists checks if a word exists in a ban list.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - banListID: The unique identifier of the ban list
//   - word: The word to check
//
// Returns:
//   - true if the word exists in the ban list
//   - false if the word does not exist in the ban list
//   - An error if the check fails
func (r *PostgresBanListRepository) WordExists(ctx context.Context, banListID int64, word string) (bool, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT EXISTS(
            SELECT 1 FROM ` + constants.TableBanListWords + `
            WHERE ` + constants.ColumnBanID + ` = $1 AND ` + constants.ColumnWord + ` = $2
        )
    `

	// Execute the query
	var exists bool
	err := r.db.QueryRowContext(ctx, query, banListID, word).Scan(&exists)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{banListID, word},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return false, fmt.Errorf("failed to check if word exists in ban list: %w", err)
	}

	return exists, nil
}
