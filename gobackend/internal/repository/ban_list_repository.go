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

// BanListRepository defines methods for interacting with ban lists
type BanListRepository interface {
	GetByID(ctx context.Context, id int64) (*models.BanList, error)
	GetBySettingID(ctx context.Context, settingID int64) (*models.BanList, error)
	CreateBanList(ctx context.Context, settingID int64) (*models.BanList, error)
	Delete(ctx context.Context, id int64) error

	// Ban list word operations
	GetBanListWords(ctx context.Context, banListID int64) ([]string, error)
	AddWords(ctx context.Context, banListID int64, words []string) error
	RemoveWords(ctx context.Context, banListID int64, words []string) error
	WordExists(ctx context.Context, banListID int64, word string) (bool, error)
}

// MysqlBanListRepository is a MySQL implementation of BanListRepository
type MysqlBanListRepository struct {
	db *database.Pool
}

// NewBanListRepository creates a new BanListRepository
func NewBanListRepository(db *database.Pool) BanListRepository {
	return &MysqlBanListRepository{
		db: db,
	}
}

// GetByID retrieves a ban list by ID
func (r *MysqlBanListRepository) GetByID(ctx context.Context, id int64) (*models.BanList, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT ban_id, setting_id
        FROM ban_lists
        WHERE ban_id = ?
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

// GetBySettingID retrieves a ban list by setting ID
func (r *MysqlBanListRepository) GetBySettingID(ctx context.Context, settingID int64) (*models.BanList, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT ban_id, setting_id
        FROM ban_lists
        WHERE setting_id = ?
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

// CreateBanList creates a new ban list for a setting
func (r *MysqlBanListRepository) CreateBanList(ctx context.Context, settingID int64) (*models.BanList, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        INSERT INTO ban_lists (setting_id)
        VALUES (?)
    `

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
		// Check for unique constraint violations
		if utils.IsDuplicateKeyError(err) {
			return nil, utils.NewDuplicateError("BanList", "setting_id", settingID)
		}
		return nil, fmt.Errorf("failed to create ban list: %w", err)
	}

	// Get the last insert ID
	banID, err := result.LastInsertId()
	if err != nil {
		return nil, fmt.Errorf("failed to get last insert ID: %w", err)
	}

	banList := &models.BanList{
		ID:        banID,
		SettingID: settingID,
	}

	log.Info().
		Int64("ban_id", banID).
		Int64("setting_id", settingID).
		Msg("Ban list created")

	return banList, nil
}

// Delete removes a ban list and all its words
func (r *MysqlBanListRepository) Delete(ctx context.Context, id int64) error {
	// Start query timer
	startTime := time.Now()

	// Execute delete within a transaction to cascade properly
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// First delete all words in the ban list
		wordQuery := "DELETE FROM ban_list_words WHERE ban_id = ?"
		_, err := tx.ExecContext(ctx, wordQuery, id)
		if err != nil {
			return fmt.Errorf("failed to delete ban list words: %w", err)
		}

		// Then delete the ban list itself
		listQuery := "DELETE FROM ban_lists WHERE ban_id = ?"
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
			Int64("ban_id", id).
			Msg("Ban list deleted")

		return nil
	})
}

// GetBanListWords retrieves all words in a ban list
func (r *MysqlBanListRepository) GetBanListWords(ctx context.Context, banListID int64) ([]string, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT word
        FROM ban_list_words
        WHERE ban_id = ?
        ORDER BY word
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

// AddWords adds words to a ban list
func (r *MysqlBanListRepository) AddWords(ctx context.Context, banListID int64, words []string) error {
	if len(words) == 0 {
		return nil
	}

	// Start query timer
	startTime := time.Now()

	// Execute within a transaction
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// Define the query
		query := `
            INSERT INTO ban_list_words (ban_id, word)
            VALUES (?, ?)
            ON DUPLICATE KEY UPDATE word = VALUES(word)
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
			Int64("ban_id", banListID).
			Int("word_count", len(words)).
			Msg("Words added to ban list")

		return nil
	})
}

// RemoveWords removes words from a ban list
func (r *MysqlBanListRepository) RemoveWords(ctx context.Context, banListID int64, words []string) error {
	if len(words) == 0 {
		return nil
	}

	// Start query timer
	startTime := time.Now()

	// Execute within a transaction
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// Define the query
		query := `
            DELETE FROM ban_list_words
            WHERE ban_id = ? AND word = ?
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
			Int64("ban_id", banListID).
			Int("word_count", len(words)).
			Msg("Words removed from ban list")

		return nil
	})
}

// WordExists checks if a word exists in a ban list
func (r *MysqlBanListRepository) WordExists(ctx context.Context, banListID int64, word string) (bool, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT EXISTS(
            SELECT 1 FROM ban_list_words
            WHERE ban_id = ? AND word = ?
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
