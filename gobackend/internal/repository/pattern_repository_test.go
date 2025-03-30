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
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
)

// setupPatternRepositoryTest creates a new test database connection and mock
func setupPatternRepositoryTest(t *testing.T) (*repository.MysqlPatternRepository, sqlmock.Sqlmock, func()) {
	// Create a new SQL mock database
	db, mock, err := sqlmock.New()
	require.NoError(t, err)

	// Create a database pool with the mock database
	dbPool := &database.Pool{DB: db}

	// Create a new repository with the mocked database
	repo := repository.NewPatternRepository(dbPool).(*repository.MysqlPatternRepository)

	// Return the repository, mock and a cleanup function
	return repo, mock, func() {
		db.Close()
	}
}

func TestPatternRepository_Create(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	pattern := &models.SearchPattern{
		SettingID:   100,
		PatternType: models.PatternTypeRegex,
		PatternText: "\\d{4}-\\d{4}-\\d{4}-\\d{4}", // Credit card pattern
	}

	// Expected query with placeholders for the arguments
	mock.ExpectExec("INSERT INTO search_patterns").
		WithArgs(pattern.SettingID, pattern.PatternType, pattern.PatternText).
		WillReturnResult(sqlmock.NewResult(1, 1))

	// Execute the method being tested
	err := repo.Create(context.Background(), pattern)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(1), pattern.ID) // ID should be set from LastInsertId
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_Create_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	pattern := &models.SearchPattern{
		SettingID:   100,
		PatternType: models.PatternTypeRegex,
		PatternText: "\\d{4}-\\d{4}-\\d{4}-\\d{4}", // Credit card pattern
	}

	// Mock database error
	mock.ExpectExec("INSERT INTO search_patterns").
		WithArgs(pattern.SettingID, pattern.PatternType, pattern.PatternText).
		WillReturnError(errors.New("database error"))

	// Execute the method being tested
	err := repo.Create(context.Background(), pattern)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to create search pattern")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_GetByID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)
	pattern := &models.SearchPattern{
		ID:          id,
		SettingID:   100,
		PatternType: models.PatternTypeRegex,
		PatternText: "\\d{4}-\\d{4}-\\d{4}-\\d{4}",
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"pattern_id", "setting_id", "pattern_type", "pattern_text"}).
		AddRow(pattern.ID, pattern.SettingID, pattern.PatternType, pattern.PatternText)

	// Expected query with placeholder for the ID
	mock.ExpectQuery("SELECT pattern_id, setting_id, pattern_type, pattern_text FROM search_patterns WHERE pattern_id = ?").
		WithArgs(id).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, pattern.ID, result.ID)
	assert.Equal(t, pattern.SettingID, result.SettingID)
	assert.Equal(t, pattern.PatternType, result.PatternType)
	assert.Equal(t, pattern.PatternText, result.PatternText)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_GetByID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Mock database response - empty result
	mock.ExpectQuery("SELECT pattern_id, setting_id, pattern_type, pattern_text FROM search_patterns WHERE pattern_id = ?").
		WithArgs(id).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_GetBySettingID(t *testing.T) {

}

func TestPatternRepository_Update(t *testing.T) {

}

func TestPatternRepository_Update_NotFound(t *testing.T) {

}

func TestPatternRepository_Delete(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Expected query with placeholder for the ID
	mock.ExpectExec("DELETE FROM search_patterns WHERE pattern_id = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_Delete_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Expected query with placeholder for the ID, but no rows affected
	mock.ExpectExec("DELETE FROM search_patterns WHERE pattern_id = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_DeleteBySettingID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)

	// Expected query with placeholder for the setting ID
	mock.ExpectExec("DELETE FROM search_patterns WHERE setting_id = ?").
		WithArgs(settingID).
		WillReturnResult(sqlmock.NewResult(0, 3)) // 3 patterns deleted

	// Execute the method being tested
	err := repo.DeleteBySettingID(context.Background(), settingID)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}
