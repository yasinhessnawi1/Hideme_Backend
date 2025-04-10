package repository_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
)

// setupSettingsRepositoryTest creates a new test database connection and mock
func setupSettingsRepositoryTest(t *testing.T) (*repository.PostgresSettingsRepository, sqlmock.Sqlmock, func()) {
	// Create a new SQL mock database
	db, mock, err := sqlmock.New()
	require.NoError(t, err)

	// Create a database pool with the mock database
	dbPool := &database.Pool{DB: db}

	// Create a new repository with the mocked database
	repo := repository.NewSettingsRepository(dbPool).(*repository.PostgresSettingsRepository)

	// Return the repository, mock and a cleanup function
	return repo, mock, func() {
		db.Close()
	}
}

func TestSettingsRepository_Create(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	settings := &models.UserSetting{
		UserID:       100,
		RemoveImages: false,
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	// Expected query with placeholders for the arguments
	mock.ExpectExec("INSERT INTO user_settings").
		WithArgs(settings.UserID, settings.RemoveImages, settings.CreatedAt, settings.UpdatedAt).
		WillReturnResult(sqlmock.NewResult(1, 1))

	// Execute the method being tested
	err := repo.Create(context.Background(), settings)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(1), settings.ID) // ID should be set from LastInsertId
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_Create_DuplicateError(t *testing.T) {

}

func TestSettingsRepository_GetByUserID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)
	now := time.Now()
	settings := &models.UserSetting{
		ID:           1,
		UserID:       userID,
		RemoveImages: true,
		CreatedAt:    now.Add(-time.Hour),
		UpdatedAt:    now,
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"setting_id", "user_id", "remove_images", "created_at", "updated_at"}).
		AddRow(settings.ID, settings.UserID, settings.RemoveImages, settings.CreatedAt, settings.UpdatedAt)

	// Expected query with placeholder for the user ID
	mock.ExpectQuery("SELECT setting_id, user_id, remove_images, created_at, updated_at FROM user_settings WHERE user_id = ?").
		WithArgs(userID).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByUserID(context.Background(), userID)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, settings.ID, result.ID)
	assert.Equal(t, settings.UserID, result.UserID)
	assert.Equal(t, settings.RemoveImages, result.RemoveImages)
	assert.WithinDuration(t, settings.CreatedAt, result.CreatedAt, time.Second)
	assert.WithinDuration(t, settings.UpdatedAt, result.UpdatedAt, time.Second)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_GetByUserID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(999)

	// Mock database response - empty result
	mock.ExpectQuery("SELECT setting_id, user_id, remove_images, created_at, updated_at FROM user_settings WHERE user_id = ?").
		WithArgs(userID).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByUserID(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_Update(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	settings := &models.UserSetting{
		ID:           1,
		UserID:       100,
		RemoveImages: true,
		CreatedAt:    now.Add(-time.Hour),
		UpdatedAt:    now,
	}

	// Expected query with placeholders for the arguments
	mock.ExpectExec("UPDATE user_settings SET remove_images = \\?, updated_at = \\? WHERE setting_id = \\?").
		WithArgs(settings.RemoveImages, settings.UpdatedAt, settings.ID).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.Update(context.Background(), settings)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_Update_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	settings := &models.UserSetting{
		ID:           999,
		UserID:       100,
		RemoveImages: true,
		CreatedAt:    now.Add(-time.Hour),
		UpdatedAt:    now,
	}

	// Expected query with placeholders for the arguments, but no rows affected
	mock.ExpectExec("UPDATE user_settings SET remove_images = \\?, updated_at = \\? WHERE setting_id = \\?").
		WithArgs(settings.RemoveImages, settings.UpdatedAt, settings.ID).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Update(context.Background(), settings)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_Delete(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Expected query with placeholder for the ID
	mock.ExpectExec("DELETE FROM user_settings WHERE setting_id = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_Delete_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Expected query with placeholder for the ID, but no rows affected
	mock.ExpectExec("DELETE FROM user_settings WHERE setting_id = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_DeleteByUserID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Expected query with placeholder for the user ID
	mock.ExpectExec("DELETE FROM user_settings WHERE user_id = ?").
		WithArgs(userID).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_DeleteByUserID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(999)

	// Expected query with placeholder for the user ID, but no rows affected
	mock.ExpectExec("DELETE FROM user_settings WHERE user_id = ?").
		WithArgs(userID).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_EnsureDefaultSettings_Existing(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)
	now := time.Now()
	settings := &models.UserSetting{
		ID:           1,
		UserID:       userID,
		RemoveImages: false,
		CreatedAt:    now.Add(-time.Hour),
		UpdatedAt:    now.Add(-time.Hour),
	}

	// Set up query result for GetByUserID
	rows := sqlmock.NewRows([]string{"setting_id", "user_id", "remove_images", "created_at", "updated_at"}).
		AddRow(settings.ID, settings.UserID, settings.RemoveImages, settings.CreatedAt, settings.UpdatedAt)

	// Expected query with placeholder for the user ID
	mock.ExpectQuery("SELECT setting_id, user_id, remove_images, created_at, updated_at FROM user_settings WHERE user_id = ?").
		WithArgs(userID).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.EnsureDefaultSettings(context.Background(), userID)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, settings.ID, result.ID)
	assert.Equal(t, settings.UserID, result.UserID)
	assert.Equal(t, settings.RemoveImages, result.RemoveImages)
	assert.WithinDuration(t, settings.CreatedAt, result.CreatedAt, time.Second)
	assert.WithinDuration(t, settings.UpdatedAt, result.UpdatedAt, time.Second)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_EnsureDefaultSettings_Create(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Mock "not found" response for GetByUserID
	mock.ExpectQuery("SELECT setting_id, user_id, remove_images, created_at, updated_at FROM user_settings WHERE user_id = ?").
		WithArgs(userID).
		WillReturnError(sql.ErrNoRows)

	// Mock Create operation with default settings
	mock.ExpectExec("INSERT INTO user_settings").
		WithArgs(
			userID,           // user_id
			false,            // remove_images (default value)
			sqlmock.AnyArg(), // created_at
			sqlmock.AnyArg(), // updated_at
		).
		WillReturnResult(sqlmock.NewResult(1, 1))

	// Execute the method being tested
	result, err := repo.EnsureDefaultSettings(context.Background(), userID)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(1), result.ID)
	assert.Equal(t, userID, result.UserID)
	assert.False(t, result.RemoveImages)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_EnsureDefaultSettings_OtherError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Mock an unexpected database error (not sql.ErrNoRows)
	dbErr := errors.New("database connection error")
	mock.ExpectQuery("SELECT setting_id, user_id, remove_images, created_at, updated_at FROM user_settings WHERE user_id = ?").
		WithArgs(userID).
		WillReturnError(dbErr)

	// Execute the method being tested
	result, err := repo.EnsureDefaultSettings(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.Equal(t, dbErr, errors.Unwrap(err))
	assert.NoError(t, mock.ExpectationsWereMet())
}
