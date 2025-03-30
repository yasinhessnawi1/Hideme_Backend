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

// setupDocumentRepositoryTest creates a new test database connection and mock
func setupDocumentRepositoryTest(t *testing.T) (*repository.MysqlDocumentRepository, sqlmock.Sqlmock, func()) {
	// Create a new SQL mock database
	db, mock, err := sqlmock.New()
	require.NoError(t, err)

	// Create a database pool with the mock database
	dbPool := &database.Pool{DB: db}

	// Create a new repository with the mocked database
	repo := repository.NewDocumentRepository(dbPool).(*repository.MysqlDocumentRepository)

	// Return the repository, mock and a cleanup function
	return repo, mock, func() {
		db.Close()
	}
}

func TestDocumentRepository_Create(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	doc := &models.Document{
		UserID:             100,
		HashedDocumentName: "hashed_name",
		UploadTimestamp:    now,
		LastModified:       now,
	}

	// Expected query with placeholders for the arguments
	mock.ExpectExec("INSERT INTO documents").
		WithArgs(doc.UserID, doc.HashedDocumentName, doc.UploadTimestamp, doc.LastModified).
		WillReturnResult(sqlmock.NewResult(1, 1))

	// Execute the method being tested
	err := repo.Create(context.Background(), doc)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(1), doc.ID) // ID should be set from LastInsertId
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_Create_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	doc := &models.Document{
		UserID:             100,
		HashedDocumentName: "hashed_name",
		UploadTimestamp:    now,
		LastModified:       now,
	}

	// Mock database error
	mock.ExpectExec("INSERT INTO documents").
		WithArgs(doc.UserID, doc.HashedDocumentName, doc.UploadTimestamp, doc.LastModified).
		WillReturnError(errors.New("database error"))

	// Execute the method being tested
	err := repo.Create(context.Background(), doc)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to create document")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetByID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)
	now := time.Now()
	doc := &models.Document{
		ID:                 id,
		UserID:             100,
		HashedDocumentName: "hashed_name",
		UploadTimestamp:    now,
		LastModified:       now,
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"document_id", "user_id", "hashed_document_name", "upload_timestamp", "last_modified"}).
		AddRow(doc.ID, doc.UserID, doc.HashedDocumentName, doc.UploadTimestamp, doc.LastModified)

	// Expected query with placeholder for the ID
	mock.ExpectQuery("SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified FROM documents WHERE document_id = ?").
		WithArgs(id).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, doc.ID, result.ID)
	assert.Equal(t, doc.UserID, result.UserID)
	assert.Equal(t, doc.HashedDocumentName, result.HashedDocumentName)
	assert.WithinDuration(t, doc.UploadTimestamp, result.UploadTimestamp, time.Second)
	assert.WithinDuration(t, doc.LastModified, result.LastModified, time.Second)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetByID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Mock database response - empty result
	mock.ExpectQuery("SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified FROM documents WHERE document_id = ?").
		WithArgs(id).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetByUserID(t *testing.T) {

}

func TestDocumentRepository_Update(t *testing.T) {

}

func TestDocumentRepository_Update_NotFound(t *testing.T) {

}

func TestDocumentRepository_Delete(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Set up transaction expectations
	mock.ExpectBegin()
	mock.ExpectExec("DELETE FROM detected_entities WHERE document_id = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 3)) // 3 entities deleted
	mock.ExpectExec("DELETE FROM documents WHERE document_id = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 1)) // 1 document deleted
	mock.ExpectCommit()

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_Delete_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Set up transaction expectations
	mock.ExpectBegin()
	mock.ExpectExec("DELETE FROM detected_entities WHERE document_id = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0)) // No entities found
	mock.ExpectExec("DELETE FROM documents WHERE document_id = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0)) // No document found
	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_DeleteByUserID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)
	docIDs := []int64{1, 2}

	// Set up transaction expectations
	mock.ExpectBegin()

	// First get document IDs
	rows := sqlmock.NewRows([]string{"document_id"})
	for _, id := range docIDs {
		rows.AddRow(id)
	}
	mock.ExpectQuery("SELECT document_id FROM documents WHERE user_id = ?").
		WithArgs(userID).
		WillReturnRows(rows)

	// Then delete entities for each document
	for _, id := range docIDs {
		mock.ExpectExec("DELETE FROM detected_entities WHERE document_id = ?").
			WithArgs(id).
			WillReturnResult(sqlmock.NewResult(0, 2)) // 2 entities per document
	}

	// Finally delete all documents
	mock.ExpectExec("DELETE FROM documents WHERE user_id = ?").
		WithArgs(userID).
		WillReturnResult(sqlmock.NewResult(0, int64(len(docIDs)))) // Number of documents deleted

	mock.ExpectCommit()

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetDetectedEntities(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	documentID := int64(1)
	now := time.Now()

	schema1 := models.RedactionSchema{
		Page:            1,
		StartX:          10.5,
		StartY:          20.5,
		EndX:            30.5,
		EndY:            40.5,
		RedactionMethod: "blackout",
	}
	_, _ = schema1.Value()

	schema2 := models.RedactionSchema{
		Page:             2,
		StartX:           15.5,
		StartY:           25.5,
		EndX:             35.5,
		EndY:             45.5,
		RedactionMethod:  "replace",
		ReplacementValue: "REDACTED",
	}
	_, _ = schema2.Value()

	entities := []*models.DetectedEntityWithMethod{
		{
			DetectedEntity: models.DetectedEntity{
				ID:                1,
				DocumentID:        documentID,
				MethodID:          1,
				EntityName:        "Credit Card",
				RedactionSchema:   schema1,
				DetectedTimestamp: now,
			},
			MethodName:     "Manual",
			HighlightColor: "#FF5733",
		},
		{
			DetectedEntity: models.DetectedEntity{
				ID:                2,
				DocumentID:        documentID,
				MethodID:          2,
				EntityName:        "SSN",
				RedactionSchema:   schema2,
				DetectedTimestamp: now.Add(time.Hour),
			},
			MethodName:     "RegexSearch",
			HighlightColor: "#33A8FF",
		},
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{
		"entity_id", "document_id", "method_id", "entity_name", "redaction_schema", "detected_timestamp",
		"method_name", "highlight_color",
	})
	for _, entity := range entities {
		schema, _ := entity.RedactionSchema.Value()
		rows.AddRow(
			entity.ID, entity.DocumentID, entity.MethodID, entity.EntityName, schema, entity.DetectedTimestamp,
			entity.MethodName, entity.HighlightColor,
		)
	}

	// Expected query with placeholder for document ID
	mock.ExpectQuery("SELECT de.entity_id, de.document_id, de.method_id, de.entity_name, de.redaction_schema, de.detected_timestamp, dm.method_name, dm.highlight_color FROM detected_entities de JOIN detection_methods dm ON de.method_id = dm.method_id WHERE de.document_id = ?").
		WithArgs(documentID).
		WillReturnRows(rows)

	// Execute the method being tested
	results, err := repo.GetDetectedEntities(context.Background(), documentID)

	// Assert the results
	assert.NoError(t, err)
	assert.Len(t, results, 2)
	for i, result := range results {
		assert.Equal(t, entities[i].ID, result.ID)
		assert.Equal(t, entities[i].DocumentID, result.DocumentID)
		assert.Equal(t, entities[i].MethodID, result.MethodID)
		assert.Equal(t, entities[i].EntityName, result.EntityName)
		assert.Equal(t, entities[i].MethodName, result.MethodName)
		assert.Equal(t, entities[i].HighlightColor, result.HighlightColor)
		assert.WithinDuration(t, entities[i].DetectedTimestamp, result.DetectedTimestamp, time.Second)
	}
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_AddDetectedEntity(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	schema := models.RedactionSchema{
		Page:            1,
		StartX:          10.5,
		StartY:          20.5,
		EndX:            30.5,
		EndY:            40.5,
		RedactionMethod: "blackout",
	}
	schemaJSON, _ := schema.Value()

	entity := &models.DetectedEntity{
		DocumentID:        1,
		MethodID:          1,
		EntityName:        "Credit Card",
		RedactionSchema:   schema,
		DetectedTimestamp: now,
	}

	// Expected query with placeholders
	mock.ExpectExec("INSERT INTO detected_entities").
		WithArgs(entity.DocumentID, entity.MethodID, entity.EntityName, schemaJSON, entity.DetectedTimestamp).
		WillReturnResult(sqlmock.NewResult(100, 1))

	// Execute the method being tested
	err := repo.AddDetectedEntity(context.Background(), entity)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(100), entity.ID) // ID should be set from LastInsertId
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_DeleteDetectedEntity(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	entityID := int64(100)

	// Expected query with placeholder for entity ID
	mock.ExpectExec("DELETE FROM detected_entities WHERE entity_id = ?").
		WithArgs(entityID).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.DeleteDetectedEntity(context.Background(), entityID)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_DeleteDetectedEntity_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	entityID := int64(999)

	// Expected query with placeholder for entity ID, but no rows affected
	mock.ExpectExec("DELETE FROM detected_entities WHERE entity_id = ?").
		WithArgs(entityID).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.DeleteDetectedEntity(context.Background(), entityID)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetDocumentSummary(t *testing.T) {

}

func TestDocumentRepository_GetDocumentSummary_NotFound(t *testing.T) {

}
