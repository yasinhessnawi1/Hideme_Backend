package repository_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
)

// setupBanListRepositoryTest creates a new test database connection and mock
func setupBanListRepositoryTest(t *testing.T) (*repository.PostgresBanListRepository, sqlmock.Sqlmock, func()) {
	// Create a new SQL mock database
	db, mock, err := sqlmock.New()
	require.NoError(t, err)

	// Create a database pool with the mock database
	dbPool := &database.Pool{DB: db}

	// Create a new repository with the mocked database
	repo := repository.NewBanListRepository(dbPool).(*repository.PostgresBanListRepository)

	// Return the repository, mock and a cleanup function
	return repo, mock, func() {
		db.Close()
	}
}

func TestBanListRepository_GetByID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)
	settingID := int64(100)

	// Set up query result
	rows := sqlmock.NewRows([]string{"ban_id", "setting_id"}).
		AddRow(id, settingID)

	// Expected query with placeholder for the ID
	mock.ExpectQuery("SELECT ban_id, setting_id FROM ban_lists WHERE ban_id = \\$1").
		WithArgs(id).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, id, result.ID)
	assert.Equal(t, settingID, result.SettingID)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestBanListRepository_GetByID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Mock database response - no rows
	mock.ExpectQuery("SELECT ban_id, setting_id FROM ban_lists WHERE ban_id = \\$1").
		WithArgs(id).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestBanListRepository_GetBySettingID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)
	settingID := int64(100)

	// Set up query result
	rows := sqlmock.NewRows([]string{"ban_id", "setting_id"}).
		AddRow(id, settingID)

	// Expected query with placeholder for the setting ID
	mock.ExpectQuery("SELECT ban_id, setting_id FROM ban_lists WHERE setting_id = \\$1").
		WithArgs(settingID).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetBySettingID(context.Background(), settingID)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, id, result.ID)
	assert.Equal(t, settingID, result.SettingID)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestBanListRepository_GetBySettingID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(999)

	// Mock database response - no rows
	mock.ExpectQuery("SELECT ban_id, setting_id FROM ban_lists WHERE setting_id = \\$1").
		WithArgs(settingID).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetBySettingID(context.Background(), settingID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestBanListRepository_CreateBanList(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)
	newID := int64(1)

	// Set up query result for the RETURNING clause
	rows := sqlmock.NewRows([]string{"ban_id"}).AddRow(newID)

	// Expected query with placeholder for the setting ID
	mock.ExpectQuery("INSERT INTO ban_lists \\(setting_id\\) VALUES \\(\\$1\\) RETURNING ban_id").
		WithArgs(settingID).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.CreateBanList(context.Background(), settingID)

	// Assert the results
	assert.NoError(t, err)
	assert.NotNil(t, result)
	assert.Equal(t, newID, result.ID)
	assert.Equal(t, settingID, result.SettingID)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestBanListRepository_CreateBanList_DuplicateError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)

	// Mock a duplicate key error - use a PostgreSQL-style error
	duplicateErr := errors.New(`pq: duplicate key value violates unique constraint "idx_setting_id_1"`)
	mock.ExpectQuery("INSERT INTO ban_lists").
		WithArgs(settingID).
		WillReturnError(duplicateErr)

	// Execute the method being tested
	result, err := repo.CreateBanList(context.Background(), settingID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestBanListRepository_Delete(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Set up transaction expectations
	mock.ExpectBegin()
	mock.ExpectExec("DELETE FROM ban_list_words WHERE ban_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 5)) // 5 related words deleted
	mock.ExpectExec("DELETE FROM ban_lists WHERE ban_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 1)) // 1 ban list deleted
	mock.ExpectCommit()

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestBanListRepository_Delete_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Set up transaction expectations
	mock.ExpectBegin()
	mock.ExpectExec("DELETE FROM ban_list_words WHERE ban_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0)) // No words found
	mock.ExpectExec("DELETE FROM ban_lists WHERE ban_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0)) // No ban list found
	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestBanListRepository_GetBanListWords(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	banListID := int64(1)
	words := []string{"word1", "word2", "word3"}

	// Set up query result
	rows := sqlmock.NewRows([]string{"word"})
	for _, word := range words {
		rows.AddRow(word)
	}

	// Expected query with placeholder for the ban list ID
	mock.ExpectQuery("SELECT word FROM ban_list_words WHERE ban_id = \\$1 ORDER BY word").
		WithArgs(banListID).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetBanListWords(context.Background(), banListID)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, words, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestBanListRepository_AddWords(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	banListID := int64(1)
	words := []string{"word1", "word2", "word3"}

	// Set up transaction expectations
	mock.ExpectBegin()
	for _, word := range words {
		mock.ExpectExec("INSERT INTO ban_list_words \\(ban_id, word\\) VALUES \\(\\$1, \\$2\\) ON CONFLICT").
			WithArgs(banListID, word).
			WillReturnResult(sqlmock.NewResult(0, 1))
	}
	mock.ExpectCommit()

	// Execute the method being tested
	err := repo.AddWords(context.Background(), banListID, words)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestBanListRepository_RemoveWords(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	banListID := int64(1)
	words := []string{"word1", "word2", "word3"}

	// Set up transaction expectations
	mock.ExpectBegin()
	for _, word := range words {
		mock.ExpectExec("DELETE FROM ban_list_words WHERE ban_id = \\$1 AND word = \\$2").
			WithArgs(banListID, word).
			WillReturnResult(sqlmock.NewResult(0, 1))
	}
	mock.ExpectCommit()

	// Execute the method being tested
	err := repo.RemoveWords(context.Background(), banListID, words)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestBanListRepository_WordExists(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	banListID := int64(1)
	word := "exists"

	// Set up query result
	rows := sqlmock.NewRows([]string{"exists"}).AddRow(true)

	// Expected query with placeholders for ban list ID and word
	mock.ExpectQuery("SELECT EXISTS").
		WithArgs(banListID, word).
		WillReturnRows(rows)

	// Execute the method being tested
	exists, err := repo.WordExists(context.Background(), banListID, word)

	// Assert the results
	assert.NoError(t, err)
	assert.True(t, exists)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestBanListRepository_WordExists_DoesNotExist(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupBanListRepositoryTest(t)
	defer cleanup()

	// Set up test data
	banListID := int64(1)
	word := "nonexistent"

	// Set up query result
	rows := sqlmock.NewRows([]string{"exists"}).AddRow(false)

	// Expected query with placeholders for ban list ID and word
	mock.ExpectQuery("SELECT EXISTS").
		WithArgs(banListID, word).
		WillReturnRows(rows)

	// Execute the method being tested
	exists, err := repo.WordExists(context.Background(), banListID, word)

	// Assert the results
	assert.NoError(t, err)
	assert.False(t, exists)
	assert.NoError(t, mock.ExpectationsWereMet())
}
