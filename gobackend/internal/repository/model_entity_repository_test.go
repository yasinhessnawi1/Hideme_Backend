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

// setupModelEntityRepositoryTest creates a new test database connection and mock
func setupModelEntityRepositoryTest(t *testing.T) (*repository.PostgresModelEntityRepository, sqlmock.Sqlmock, func()) {
	// Create a new SQL mock database
	db, mock, err := sqlmock.New()
	require.NoError(t, err)

	// Create a database pool with the mock database
	dbPool := &database.Pool{DB: db}

	// Create a new repository with the mocked database
	repo := repository.NewModelEntityRepository(dbPool).(*repository.PostgresModelEntityRepository)

	// Return the repository, mock and a cleanup function
	return repo, mock, func() {
		db.Close()
	}
}

func TestModelEntityRepository_Create(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	entity := &models.ModelEntity{
		SettingID:  100,
		MethodID:   5,
		EntityText: "Credit Card",
	}

	// Set up for PostgreSQL RETURNING clause
	rows := sqlmock.NewRows([]string{"model_entity_id"}).AddRow(1)

	// Expected query with placeholders for the arguments
	mock.ExpectQuery("INSERT INTO model_entities").
		WithArgs(entity.SettingID, entity.MethodID, entity.EntityText).
		WillReturnRows(rows)

	// Execute the method being tested
	err := repo.Create(context.Background(), entity)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(1), entity.ID) // ID should be set from RETURNING clause
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_Create_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	entity := &models.ModelEntity{
		SettingID:  100,
		MethodID:   5,
		EntityText: "Credit Card",
	}

	// Mock database error
	mock.ExpectQuery("INSERT INTO model_entities").
		WithArgs(entity.SettingID, entity.MethodID, entity.EntityText).
		WillReturnError(errors.New("database error"))

	// Execute the method being tested
	err := repo.Create(context.Background(), entity)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to create model entity")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_CreateBatch(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	entities := []*models.ModelEntity{
		{
			SettingID:  100,
			MethodID:   5,
			EntityText: "Credit Card",
		},
		{
			SettingID:  100,
			MethodID:   5,
			EntityText: "SSN",
		},
	}

	// Set up transaction expectations
	mock.ExpectBegin()

	// For PostgreSQL, each entity insertion returns its ID
	rows1 := sqlmock.NewRows([]string{"model_entity_id"}).AddRow(1)
	rows2 := sqlmock.NewRows([]string{"model_entity_id"}).AddRow(2)

	// Each entity will be inserted
	mock.ExpectQuery("INSERT INTO model_entities").
		WithArgs(entities[0].SettingID, entities[0].MethodID, entities[0].EntityText).
		WillReturnRows(rows1)

	mock.ExpectQuery("INSERT INTO model_entities").
		WithArgs(entities[1].SettingID, entities[1].MethodID, entities[1].EntityText).
		WillReturnRows(rows2)

	mock.ExpectCommit()

	// Execute the method being tested
	err := repo.CreateBatch(context.Background(), entities)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(1), entities[0].ID) // IDs should be set from query results
	assert.Equal(t, int64(2), entities[1].ID)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_CreateBatch_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	entities := []*models.ModelEntity{
		{
			SettingID:  100,
			MethodID:   5,
			EntityText: "Credit Card",
		},
		{
			SettingID:  100,
			MethodID:   5,
			EntityText: "SSN",
		},
	}

	// Set up transaction expectations with error
	mock.ExpectBegin()

	// First entity inserts successfully
	rows1 := sqlmock.NewRows([]string{"model_entity_id"}).AddRow(1)
	mock.ExpectQuery("INSERT INTO model_entities").
		WithArgs(entities[0].SettingID, entities[0].MethodID, entities[0].EntityText).
		WillReturnRows(rows1)

	// Second entity fails
	mock.ExpectQuery("INSERT INTO model_entities").
		WithArgs(entities[1].SettingID, entities[1].MethodID, entities[1].EntityText).
		WillReturnError(errors.New("database error"))

	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.CreateBatch(context.Background(), entities)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to create model entity")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_GetByID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)
	entity := &models.ModelEntity{
		ID:         id,
		SettingID:  100,
		MethodID:   5,
		EntityText: "Credit Card",
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"model_entity_id", "setting_id", "method_id", "entity_text"}).
		AddRow(entity.ID, entity.SettingID, entity.MethodID, entity.EntityText)

	// Expected query with placeholder for the ID
	mock.ExpectQuery("SELECT model_entity_id, setting_id, method_id, entity_text FROM model_entities WHERE model_entity_id = \\$1").
		WithArgs(id).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, entity.ID, result.ID)
	assert.Equal(t, entity.SettingID, result.SettingID)
	assert.Equal(t, entity.MethodID, result.MethodID)
	assert.Equal(t, entity.EntityText, result.EntityText)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_GetByID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Mock database response - empty result
	mock.ExpectQuery("SELECT model_entity_id, setting_id, method_id, entity_text FROM model_entities WHERE model_entity_id = \\$1").
		WithArgs(id).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_GetBySettingID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)
	entities := []*models.ModelEntity{
		{
			ID:         1,
			SettingID:  settingID,
			MethodID:   5,
			EntityText: "Credit Card",
		},
		{
			ID:         2,
			SettingID:  settingID,
			MethodID:   6,
			EntityText: "SSN",
		},
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"model_entity_id", "setting_id", "method_id", "entity_text"})
	for _, entity := range entities {
		rows.AddRow(entity.ID, entity.SettingID, entity.MethodID, entity.EntityText)
	}

	// Expected query with placeholder for the setting ID
	mock.ExpectQuery("SELECT model_entity_id, setting_id, method_id, entity_text FROM model_entities WHERE setting_id = \\$1 ORDER BY method_id, entity_text").
		WithArgs(settingID).
		WillReturnRows(rows)

	// Execute the method being tested
	results, err := repo.GetBySettingID(context.Background(), settingID)

	// Assert the results
	assert.NoError(t, err)
	assert.Len(t, results, 2)
	assert.Equal(t, entities[0].ID, results[0].ID)
	assert.Equal(t, entities[1].ID, results[1].ID)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_GetBySettingIDAndMethodID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)
	methodID := int64(5)
	entities := []*models.ModelEntityWithMethod{
		{
			ModelEntity: models.ModelEntity{
				ID:         1,
				SettingID:  settingID,
				MethodID:   methodID,
				EntityText: "Credit Card",
			},
			MethodName: "Regex Search",
		},
		{
			ModelEntity: models.ModelEntity{
				ID:         2,
				SettingID:  settingID,
				MethodID:   methodID,
				EntityText: "SSN",
			},
			MethodName: "Regex Search",
		},
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"model_entity_id", "setting_id", "method_id", "entity_text", "method_name"})
	for _, entity := range entities {
		rows.AddRow(entity.ID, entity.SettingID, entity.MethodID, entity.EntityText, entity.MethodName)
	}

	// Expected query with placeholder for setting ID and method ID
	mock.ExpectQuery("SELECT me.model_entity_id, me.setting_id, me.method_id, me.entity_text, dm.method_name FROM model_entities me JOIN detection_methods dm ON me.method_id = dm.method_id WHERE me.setting_id = \\$1 AND me.method_id = \\$2 ORDER BY me.entity_text").
		WithArgs(settingID, methodID).
		WillReturnRows(rows)

	// Execute the method being tested
	results, err := repo.GetBySettingIDAndMethodID(context.Background(), settingID, methodID)

	// Assert the results
	assert.NoError(t, err)
	assert.Len(t, results, 2)
	assert.Equal(t, entities[0].ID, results[0].ID)
	assert.Equal(t, entities[0].MethodName, results[0].MethodName)
	assert.Equal(t, entities[1].ID, results[1].ID)
	assert.Equal(t, entities[1].MethodName, results[1].MethodName)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_Update(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	entity := &models.ModelEntity{
		ID:         1,
		SettingID:  100,
		MethodID:   5,
		EntityText: "Updated Text",
	}

	// Expected query with placeholders
	mock.ExpectExec("UPDATE model_entities SET entity_text = \\$1 WHERE model_entity_id = \\$2").
		WithArgs(entity.EntityText, entity.ID).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.Update(context.Background(), entity)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_Update_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	entity := &models.ModelEntity{
		ID:         999,
		SettingID:  100,
		MethodID:   5,
		EntityText: "Updated Text",
	}

	// Expected query with placeholders, but no rows affected
	mock.ExpectExec("UPDATE model_entities SET entity_text = \\$1 WHERE model_entity_id = \\$2").
		WithArgs(entity.EntityText, entity.ID).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Update(context.Background(), entity)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_Delete(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Expected query with placeholder for the ID
	mock.ExpectExec("DELETE FROM model_entities WHERE model_entity_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_Delete_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Expected query with placeholder for the ID, but no rows affected
	mock.ExpectExec("DELETE FROM model_entities WHERE model_entity_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_DeleteBySettingID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)

	// Expected query with placeholder for the setting ID
	mock.ExpectExec("DELETE FROM model_entities WHERE setting_id = \\$1").
		WithArgs(settingID).
		WillReturnResult(sqlmock.NewResult(0, 3)) // 3 entities deleted

	// Execute the method being tested
	err := repo.DeleteBySettingID(context.Background(), settingID)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestModelEntityRepository_DeleteByMethodID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupModelEntityRepositoryTest(t)
	defer cleanup()

	// Set up test data
	settingID := int64(100)
	methodID := int64(5)

	// Expected query with placeholders for setting ID and method ID
	mock.ExpectExec("DELETE FROM model_entities WHERE setting_id = \\$1 AND method_id = \\$2").
		WithArgs(settingID, methodID).
		WillReturnResult(sqlmock.NewResult(0, 2)) // 2 entities deleted

	// Execute the method being tested
	err := repo.DeleteByMethodID(context.Background(), settingID, methodID)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}
