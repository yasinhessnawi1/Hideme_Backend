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
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
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

/*
func TestSettingsRepository_Create(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	settings := &models.UserSetting{
		UserID:                 100,
		RemoveImages:           false,
		Theme:                  "system",
		DetectionThreshold:     0.5,
		UseBanlistForDetection: true,
		AutoProcessing:         true,
		CreatedAt:              now,
		UpdatedAt:              now,
	}

	// Setup for PostgreSQL RETURNING clause
	rows := sqlmock.NewRows([]string{"setting_id"}).AddRow(1)

	// Expected query with placeholders for the arguments
	mock.ExpectQuery("INSERT INTO user_settings").
		WithArgs(
			settings.UserID,
			settings.RemoveImages,
			settings.Theme,
			settings.DetectionThreshold,
			settings.UseBanlistForDetection,
			settings.AutoProcessing,
			settings.CreatedAt,
			settings.UpdatedAt,
		).
		WillReturnRows(rows)

	// Execute the method being tested
	err := repo.Create(context.Background(), settings)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(1), settings.ID) // ID should be set from RETURNING clause
	assert.NoError(t, mock.ExpectationsWereMet())
}
*/

func TestSettingsRepository_Create_DuplicateError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data with minimal fields, allowing repository to handle timestamps
	settings := &models.UserSetting{
		UserID:                 100,
		RemoveImages:           false,
		Theme:                  "system",
		DetectionThreshold:     0.5,
		UseBanlistForDetection: true,
		AutoProcessing:         true,
		// Not setting CreatedAt and UpdatedAt explicitly
	}

	// Use a string error that contains "duplicate" for the test
	duplicateErr := errors.New("pq: duplicate key value violates unique constraint \"idx_user_id\"")

	mock.ExpectQuery("INSERT INTO user_settings").
		WithArgs(
			settings.UserID,
			settings.RemoveImages,
			settings.Theme,
			settings.DetectionThreshold,
			settings.UseBanlistForDetection,
			settings.AutoProcessing,
			sqlmock.AnyArg(), // CreatedAt - accept any timestamp
			sqlmock.AnyArg(), // UpdatedAt - accept any timestamp
		).
		WillReturnError(duplicateErr)

	// Execute the method being tested
	err := repo.Create(context.Background(), settings)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "duplicate")
	assert.NoError(t, mock.ExpectationsWereMet())
}

/*
func TestSettingsRepository_Create_OtherError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	settings := &models.UserSetting{
		UserID:                 100,
		RemoveImages:           false,
		Theme:                  "system",
		DetectionThreshold:     0.5,
		UseBanlistForDetection: true,
		AutoProcessing:         true,
		CreatedAt:              now,
		UpdatedAt:              now,
	}

	// Mock a different database error
	otherErr := errors.New("database connection failed")

	mock.ExpectQuery("INSERT INTO user_settings").
		WithArgs(
			settings.UserID,
			settings.RemoveImages,
			settings.Theme,
			settings.DetectionThreshold,
			settings.UseBanlistForDetection,
			settings.AutoProcessing,
			settings.CreatedAt,
			settings.UpdatedAt,
		).
		WillReturnError(otherErr)

	// Execute the method being tested
	err := repo.Create(context.Background(), settings)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to create user settings")
	assert.NoError(t, mock.ExpectationsWereMet())
}

*/

func TestSettingsRepository_GetByUserID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)
	now := time.Now()
	settings := &models.UserSetting{
		ID:                     1,
		UserID:                 userID,
		RemoveImages:           true,
		Theme:                  "dark",
		DetectionThreshold:     0.7,
		UseBanlistForDetection: true,
		AutoProcessing:         false,
		CreatedAt:              now.Add(-time.Hour),
		UpdatedAt:              now,
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{
		"setting_id", "user_id", "remove_images", "theme",
		"detection_threshold", "use_banlist_for_detection", "auto_processing",
		"created_at", "updated_at",
	}).AddRow(
		settings.ID, settings.UserID, settings.RemoveImages, settings.Theme,
		settings.DetectionThreshold, settings.UseBanlistForDetection, settings.AutoProcessing,
		settings.CreatedAt, settings.UpdatedAt,
	)

	// Expected query with placeholder for the user ID
	mock.ExpectQuery("SELECT setting_id, user_id, remove_images, theme, detection_threshold, use_banlist_for_detection, auto_processing, created_at, updated_at FROM user_settings WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByUserID(context.Background(), userID)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, settings.ID, result.ID)
	assert.Equal(t, settings.UserID, result.UserID)
	assert.Equal(t, settings.RemoveImages, result.RemoveImages)
	assert.Equal(t, settings.Theme, result.Theme)
	assert.Equal(t, settings.DetectionThreshold, result.DetectionThreshold)
	assert.Equal(t, settings.UseBanlistForDetection, result.UseBanlistForDetection)
	assert.Equal(t, settings.AutoProcessing, result.AutoProcessing)
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
	mock.ExpectQuery("SELECT setting_id, user_id, remove_images, theme, detection_threshold, use_banlist_for_detection, auto_processing, created_at, updated_at FROM user_settings WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByUserID(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_GetByUserID_OtherError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Mock a different database error
	otherErr := errors.New("database query failed")

	mock.ExpectQuery("SELECT setting_id, user_id, remove_images, theme, detection_threshold, use_banlist_for_detection, auto_processing, created_at, updated_at FROM user_settings WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnError(otherErr)

	// Execute the method being tested
	result, err := repo.GetByUserID(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.Contains(t, err.Error(), "failed to get user settings by user ID")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_Update(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	settings := &models.UserSetting{
		ID:                     1,
		UserID:                 100,
		RemoveImages:           true,
		Theme:                  "dark",
		DetectionThreshold:     0.8,
		UseBanlistForDetection: false,
		AutoProcessing:         false,
		CreatedAt:              now.Add(-time.Hour),
		UpdatedAt:              now,
	}

	// Expected query with placeholders
	mock.ExpectExec("UPDATE user_settings SET remove_images = \\$1, theme = \\$2, detection_threshold = \\$3, use_banlist_for_detection = \\$4, auto_processing = \\$5, updated_at = \\$6 WHERE setting_id = \\$7").
		WithArgs(
			settings.RemoveImages,
			settings.Theme,
			settings.DetectionThreshold,
			settings.UseBanlistForDetection,
			settings.AutoProcessing,
			sqlmock.AnyArg(),
			settings.ID,
		).
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
		ID:                     999,
		UserID:                 100,
		RemoveImages:           true,
		Theme:                  "dark",
		DetectionThreshold:     0.8,
		UseBanlistForDetection: false,
		AutoProcessing:         false,
		CreatedAt:              now.Add(-time.Hour),
		UpdatedAt:              now,
	}

	// Expected query with placeholders, but no rows affected
	mock.ExpectExec("UPDATE user_settings SET remove_images = \\$1, theme = \\$2, detection_threshold = \\$3, use_banlist_for_detection = \\$4, auto_processing = \\$5, updated_at = \\$6 WHERE setting_id = \\$7").
		WithArgs(
			settings.RemoveImages,
			settings.Theme,
			settings.DetectionThreshold,
			settings.UseBanlistForDetection,
			settings.AutoProcessing,
			sqlmock.AnyArg(),
			settings.ID,
		).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Update(context.Background(), settings)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not found")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_Update_ErrorGettingRowsAffected(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	settings := &models.UserSetting{
		ID:                     1,
		UserID:                 100,
		RemoveImages:           true,
		Theme:                  "dark",
		DetectionThreshold:     0.8,
		UseBanlistForDetection: false,
		AutoProcessing:         false,
		CreatedAt:              now.Add(-time.Hour),
		UpdatedAt:              now,
	}

	// Create a result that will error on RowsAffected
	result := sqlmock.NewErrorResult(errors.New("rows affected error"))

	// Expected query with placeholders
	mock.ExpectExec("UPDATE user_settings SET remove_images = \\$1, theme = \\$2, detection_threshold = \\$3, use_banlist_for_detection = \\$4, auto_processing = \\$5, updated_at = \\$6 WHERE setting_id = \\$7").
		WithArgs(
			settings.RemoveImages,
			settings.Theme,
			settings.DetectionThreshold,
			settings.UseBanlistForDetection,
			settings.AutoProcessing,
			sqlmock.AnyArg(),
			settings.ID,
		).
		WillReturnResult(result)

	// Execute the method being tested
	err := repo.Update(context.Background(), settings)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get rows affected")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_Update_ExecError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	settings := &models.UserSetting{
		ID:                     1,
		UserID:                 100,
		RemoveImages:           true,
		Theme:                  "dark",
		DetectionThreshold:     0.8,
		UseBanlistForDetection: false,
		AutoProcessing:         false,
		CreatedAt:              now.Add(-time.Hour),
		UpdatedAt:              now,
	}

	// Mock a database error
	execErr := errors.New("exec error")

	// Expected query with placeholders
	mock.ExpectExec("UPDATE user_settings SET remove_images = \\$1, theme = \\$2, detection_threshold = \\$3, use_banlist_for_detection = \\$4, auto_processing = \\$5, updated_at = \\$6 WHERE setting_id = \\$7").
		WithArgs(
			settings.RemoveImages,
			settings.Theme,
			settings.DetectionThreshold,
			settings.UseBanlistForDetection,
			settings.AutoProcessing,
			sqlmock.AnyArg(),
			settings.ID,
		).
		WillReturnError(execErr)

	// Execute the method being tested
	err := repo.Update(context.Background(), settings)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to update user settings")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_Delete(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Expected query with placeholder for the ID
	mock.ExpectExec("DELETE FROM user_settings WHERE setting_id = \\$1").
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
	mock.ExpectExec("DELETE FROM user_settings WHERE setting_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not found")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_Delete_ErrorGettingRowsAffected(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Create a result that will error on RowsAffected
	result := sqlmock.NewErrorResult(errors.New("rows affected error"))

	// Expected query with placeholder for the ID
	mock.ExpectExec("DELETE FROM user_settings WHERE setting_id = \\$1").
		WithArgs(id).
		WillReturnResult(result)

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get rows affected")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_Delete_ExecError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Mock a database error
	execErr := errors.New("exec error")

	// Expected query with placeholder for the ID
	mock.ExpectExec("DELETE FROM user_settings WHERE setting_id = \\$1").
		WithArgs(id).
		WillReturnError(execErr)

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to delete user settings")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_DeleteByUserID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Expected query with placeholder for the user ID
	mock.ExpectExec("DELETE FROM user_settings WHERE user_id = \\$1").
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
	mock.ExpectExec("DELETE FROM user_settings WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not found")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_DeleteByUserID_ErrorGettingRowsAffected(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Create a result that will error on RowsAffected
	result := sqlmock.NewErrorResult(errors.New("rows affected error"))

	// Expected query with placeholder for the user ID
	mock.ExpectExec("DELETE FROM user_settings WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnResult(result)

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get rows affected")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_DeleteByUserID_ExecError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Mock a database error
	execErr := errors.New("exec error")

	// Expected query with placeholder for the user ID
	mock.ExpectExec("DELETE FROM user_settings WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnError(execErr)

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to delete user settings by user ID")
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
		ID:                     1,
		UserID:                 userID,
		RemoveImages:           false,
		Theme:                  "system",
		DetectionThreshold:     0.5,
		UseBanlistForDetection: true,
		AutoProcessing:         true,
		CreatedAt:              now.Add(-time.Hour),
		UpdatedAt:              now.Add(-time.Hour),
	}

	// Set up query result for GetByUserID
	rows := sqlmock.NewRows([]string{
		"setting_id", "user_id", "remove_images", "theme",
		"detection_threshold", "use_banlist_for_detection", "auto_processing",
		"created_at", "updated_at",
	}).AddRow(
		settings.ID, settings.UserID, settings.RemoveImages, settings.Theme,
		settings.DetectionThreshold, settings.UseBanlistForDetection, settings.AutoProcessing,
		settings.CreatedAt, settings.UpdatedAt,
	)

	// Expected query with placeholder for the user ID
	mock.ExpectQuery("SELECT setting_id, user_id, remove_images, theme, detection_threshold, use_banlist_for_detection, auto_processing, created_at, updated_at FROM user_settings WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.EnsureDefaultSettings(context.Background(), userID)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, settings.ID, result.ID)
	assert.Equal(t, settings.UserID, result.UserID)
	assert.Equal(t, settings.RemoveImages, result.RemoveImages)
	assert.Equal(t, settings.Theme, result.Theme)
	assert.Equal(t, settings.DetectionThreshold, result.DetectionThreshold)
	assert.Equal(t, settings.UseBanlistForDetection, result.UseBanlistForDetection)
	assert.Equal(t, settings.AutoProcessing, result.AutoProcessing)
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

	// Mock a "not found" error for the first GetByUserID call
	mock.ExpectQuery("SELECT setting_id, user_id, remove_images, theme, detection_threshold, use_banlist_for_detection, auto_processing, created_at, updated_at FROM user_settings WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnError(sql.ErrNoRows)

	// Setup expectations for the create call
	// The expected default values are defined in models.NewUserSetting
	mock.ExpectQuery("INSERT INTO user_settings").
		WithArgs(
			userID,
			true,             // Default RemoveImages
			"system",         // Default Theme
			0.5,              // Default DetectionThreshold
			true,             // Default UseBanlistForDetection
			true,             // Default AutoProcessing
			sqlmock.AnyArg(), // CreatedAt
			sqlmock.AnyArg(), // UpdatedAt
		).
		WillReturnRows(sqlmock.NewRows([]string{"setting_id"}).AddRow(1))

	// Execute the method being tested
	result, err := repo.EnsureDefaultSettings(context.Background(), userID)

	// Assert the results
	assert.NoError(t, err)
	assert.NotNil(t, result)
	assert.Equal(t, int64(1), result.ID)
	assert.Equal(t, userID, result.UserID)
	assert.Equal(t, true, result.RemoveImages) // These are the default values from models.NewUserSetting
	assert.Equal(t, "system", result.Theme)
	assert.Equal(t, 0.5, result.DetectionThreshold)
	assert.Equal(t, true, result.UseBanlistForDetection)
	assert.Equal(t, true, result.AutoProcessing)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSettingsRepository_EnsureDefaultSettings_CreateError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSettingsRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Mock a "not found" error for the first GetByUserID call
	mock.ExpectQuery("SELECT setting_id, user_id, remove_images, theme, detection_threshold, use_banlist_for_detection, auto_processing, created_at, updated_at FROM user_settings WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnError(sql.ErrNoRows)

	// Mock an error during the create operation
	createErr := errors.New("database insert error")
	mock.ExpectQuery("INSERT INTO user_settings").
		WithArgs(
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
		).
		WillReturnError(createErr)

	// Execute the method being tested
	result, err := repo.EnsureDefaultSettings(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.Contains(t, err.Error(), "failed to create default settings")
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
	mock.ExpectQuery("SELECT setting_id, user_id, remove_images, theme, detection_threshold, use_banlist_for_detection, auto_processing, created_at, updated_at FROM user_settings WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnError(dbErr)

	// Execute the method being tested
	result, err := repo.EnsureDefaultSettings(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.Contains(t, err.Error(), "failed to get user settings")
	assert.NoError(t, mock.ExpectationsWereMet())
}

// Test that when checking for a NotFound error, it correctly identifies it
func TestSettingsRepository_IsNotFoundError(t *testing.T) {
	// Create a NotFound error
	notFoundErr := utils.NewNotFoundError("UserSetting", 1)

	// Check that it's correctly identified
	assert.True(t, utils.IsNotFoundError(notFoundErr))
}
