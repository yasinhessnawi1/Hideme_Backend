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
func setupPatternRepositoryTest(t *testing.T) (*repository.PostgresPatternRepository, sqlmock.Sqlmock, func()) {
	// Create a new SQL mock database
	db, mock, err := sqlmock.New()
	require.NoError(t, err)

	// Create a database pool with the mock database
	dbPool := &database.Pool{DB: db}

	// Create a new repository with the mocked database
	repo := repository.NewPatternRepository(dbPool).(*repository.PostgresPatternRepository)

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
		PatternType: models.PatternType("regex"),
		PatternText: "\\d{4}-\\d{4}-\\d{4}-\\d{4}", // Credit card pattern
	}

	// Set up for PostgreSQL RETURNING clause
	rows := sqlmock.NewRows([]string{"pattern_id"}).AddRow(1)

	// Expected query with placeholders for the arguments
	mock.ExpectQuery("INSERT INTO search_patterns").
		WithArgs(pattern.SettingID, pattern.PatternType, pattern.PatternText).
		WillReturnRows(rows)

	// Execute the method being tested
	err := repo.Create(context.Background(), pattern)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(1), pattern.ID) // ID should be set from RETURNING clause
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_Create_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	pattern := &models.SearchPattern{
		SettingID:   100,
		PatternType: models.PatternType("regex"),
		PatternText: "\\d{4}-\\d{4}-\\d{4}-\\d{4}", // Credit card pattern
	}

	// Mock database error
	mock.ExpectQuery("INSERT INTO search_patterns").
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
		PatternType: models.PatternType("regex"),
		PatternText: "\\d{4}-\\d{4}-\\d{4}-\\d{4}",
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"pattern_id", "setting_id", "pattern_type", "pattern_text"}).
		AddRow(pattern.ID, pattern.SettingID, string(pattern.PatternType), pattern.PatternText)

	// Expected query with placeholder for the ID
	mock.ExpectQuery("SELECT pattern_id, setting_id, pattern_type, pattern_text FROM search_patterns WHERE pattern_id = \\$1").
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
	mock.ExpectQuery("SELECT pattern_id, setting_id, pattern_type, pattern_text FROM search_patterns WHERE pattern_id = \\$1").
		WithArgs(id).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_GetByID_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Mock general database error
	mock.ExpectQuery("SELECT pattern_id, setting_id, pattern_type, pattern_text FROM search_patterns WHERE pattern_id = \\$1").
		WithArgs(id).
		WillReturnError(errors.New("database error"))

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get search pattern by ID")
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_GetBySettingID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)
	patterns := []*models.SearchPattern{
		{
			ID:          1,
			SettingID:   settingID,
			PatternType: models.PatternType("regex"),
			PatternText: "\\d{4}-\\d{4}-\\d{4}-\\d{4}",
		},
		{
			ID:          2,
			SettingID:   settingID,
			PatternType: models.PatternType("keyword"),
			PatternText: "credit card",
		},
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"pattern_id", "setting_id", "pattern_type", "pattern_text"})
	for _, pattern := range patterns {
		rows.AddRow(pattern.ID, pattern.SettingID, string(pattern.PatternType), pattern.PatternText)
	}

	// Expected query with placeholder for the setting ID
	mock.ExpectQuery("SELECT pattern_id, setting_id, pattern_type, pattern_text FROM search_patterns WHERE setting_id = \\$1 ORDER BY pattern_id").
		WithArgs(settingID).
		WillReturnRows(rows)

	// Execute the method being tested
	results, err := repo.GetBySettingID(context.Background(), settingID)

	// Assert the results
	assert.NoError(t, err)
	assert.Len(t, results, 2)
	assert.Equal(t, patterns[0].ID, results[0].ID)
	assert.Equal(t, patterns[1].ID, results[1].ID)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_GetBySettingID_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)

	// Mock database error
	mock.ExpectQuery("SELECT pattern_id, setting_id, pattern_type, pattern_text FROM search_patterns WHERE setting_id = \\$1 ORDER BY pattern_id").
		WithArgs(settingID).
		WillReturnError(errors.New("database error"))

	// Execute the method being tested
	results, err := repo.GetBySettingID(context.Background(), settingID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get search patterns by setting ID")
	assert.Nil(t, results)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_GetBySettingID_ScanError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)

	// Create rows with invalid data to cause scan error
	rows := sqlmock.NewRows([]string{"pattern_id", "setting_id", "pattern_type", "pattern_text"}).
		AddRow("invalid_id", settingID, "regex", "pattern") // invalid_id should cause scan error

	mock.ExpectQuery("SELECT pattern_id, setting_id, pattern_type, pattern_text FROM search_patterns WHERE setting_id = \\$1 ORDER BY pattern_id").
		WithArgs(settingID).
		WillReturnRows(rows)

	// Execute the method being tested
	results, err := repo.GetBySettingID(context.Background(), settingID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to scan search pattern row")
	assert.Nil(t, results)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_GetBySettingID_RowsError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)

	// Create rows with a row error
	rows := sqlmock.NewRows([]string{"pattern_id", "setting_id", "pattern_type", "pattern_text"}).
		AddRow(1, settingID, "regex", "pattern").
		RowError(0, errors.New("row error"))

	mock.ExpectQuery("SELECT pattern_id, setting_id, pattern_type, pattern_text FROM search_patterns WHERE setting_id = \\$1 ORDER BY pattern_id").
		WithArgs(settingID).
		WillReturnRows(rows)

	// Execute the method being tested
	results, err := repo.GetBySettingID(context.Background(), settingID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "error iterating search pattern rows")
	assert.Nil(t, results)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_GetBySettingID_EmptyResult(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)

	// Create empty rows to test the empty result scenario
	rows := sqlmock.NewRows([]string{"pattern_id", "setting_id", "pattern_type", "pattern_text"})

	mock.ExpectQuery("SELECT pattern_id, setting_id, pattern_type, pattern_text FROM search_patterns WHERE setting_id = \\$1 ORDER BY pattern_id").
		WithArgs(settingID).
		WillReturnRows(rows)

	// Execute the method being tested
	results, err := repo.GetBySettingID(context.Background(), settingID)

	// Assert the results
	assert.NoError(t, err)
	assert.Empty(t, results)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_Update(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	pattern := &models.SearchPattern{
		ID:          1,
		SettingID:   100,
		PatternType: models.PatternType("regex"),
		PatternText: "\\d{4}-\\d{4}-\\d{4}-\\d{4}\\|\\d{16}",
	}

	// Expected query with placeholders
	mock.ExpectExec("UPDATE search_patterns SET pattern_type = \\$1, pattern_text = \\$2 WHERE pattern_id = \\$3").
		WithArgs(pattern.PatternType, pattern.PatternText, pattern.ID).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.Update(context.Background(), pattern)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_Update_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	pattern := &models.SearchPattern{
		ID:          999,
		SettingID:   100,
		PatternType: models.PatternType("regex"),
		PatternText: "updated pattern",
	}

	// Expected query with placeholders, but no rows affected
	mock.ExpectExec("UPDATE search_patterns SET pattern_type = \\$1, pattern_text = \\$2 WHERE pattern_id = \\$3").
		WithArgs(pattern.PatternType, pattern.PatternText, pattern.ID).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Update(context.Background(), pattern)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_Update_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	pattern := &models.SearchPattern{
		ID:          1,
		SettingID:   100,
		PatternType: models.PatternType("regex"),
		PatternText: "\\d{4}-\\d{4}-\\d{4}-\\d{4}",
	}

	// Mock database error
	mock.ExpectExec("UPDATE search_patterns SET pattern_type = \\$1, pattern_text = \\$2 WHERE pattern_id = \\$3").
		WithArgs(pattern.PatternType, pattern.PatternText, pattern.ID).
		WillReturnError(errors.New("database error"))

	// Execute the method being tested
	err := repo.Update(context.Background(), pattern)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to update search pattern")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_Update_RowsAffectedError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	pattern := &models.SearchPattern{
		ID:          1,
		SettingID:   100,
		PatternType: models.PatternType("regex"),
		PatternText: "\\d{4}-\\d{4}-\\d{4}-\\d{4}",
	}

	// Create a custom result that returns an error for RowsAffected()
	result := sqlmock.NewErrorResult(errors.New("rows affected error"))

	// Expected query with placeholders
	mock.ExpectExec("UPDATE search_patterns SET pattern_type = \\$1, pattern_text = \\$2 WHERE pattern_id = \\$3").
		WithArgs(pattern.PatternType, pattern.PatternText, pattern.ID).
		WillReturnResult(result)

	// Execute the method being tested
	err := repo.Update(context.Background(), pattern)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get rows affected")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_Delete(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Expected query with placeholder for the ID
	mock.ExpectExec("DELETE FROM search_patterns WHERE pattern_id = \\$1").
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
	mock.ExpectExec("DELETE FROM search_patterns WHERE pattern_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_Delete_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Mock database error
	mock.ExpectExec("DELETE FROM search_patterns WHERE pattern_id = \\$1").
		WithArgs(id).
		WillReturnError(errors.New("database error"))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to delete search pattern")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_Delete_RowsAffectedError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Create a custom result that returns an error for RowsAffected()
	result := sqlmock.NewErrorResult(errors.New("rows affected error"))

	// Expected query with placeholder for the ID
	mock.ExpectExec("DELETE FROM search_patterns WHERE pattern_id = \\$1").
		WithArgs(id).
		WillReturnResult(result)

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get rows affected")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_DeleteBySettingID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)

	// Expected query with placeholder for the setting ID
	mock.ExpectExec("DELETE FROM search_patterns WHERE setting_id = \\$1").
		WithArgs(settingID).
		WillReturnResult(sqlmock.NewResult(0, 3)) // 3 patterns deleted

	// Execute the method being tested
	err := repo.DeleteBySettingID(context.Background(), settingID)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestPatternRepository_DeleteBySettingID_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupPatternRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)

	// Mock database error
	mock.ExpectExec("DELETE FROM search_patterns WHERE setting_id = \\$1").
		WithArgs(settingID).
		WillReturnError(errors.New("database error"))

	// Execute the method being tested
	err := repo.DeleteBySettingID(context.Background(), settingID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to delete search patterns by setting ID")
	assert.NoError(t, mock.ExpectationsWereMet())
}
