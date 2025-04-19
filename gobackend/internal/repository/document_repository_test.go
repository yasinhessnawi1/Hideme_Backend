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
func setupDocumentRepositoryTest(t *testing.T) (*repository.PostgresDocumentRepository, sqlmock.Sqlmock, func()) {
	// Create a new SQL mock database
	db, mock, err := sqlmock.New()
	require.NoError(t, err)

	// Create a database pool with the mock database
	dbPool := &database.Pool{DB: db}

	// Create a new repository with the mocked database
	repo := repository.NewDocumentRepository(dbPool).(*repository.PostgresDocumentRepository)

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

	// Setup for PostgreSQL RETURNING clause
	rows := sqlmock.NewRows([]string{"document_id"}).AddRow(1)

	// Expected query with placeholders for the arguments
	mock.ExpectQuery("INSERT INTO documents").
		WithArgs(doc.UserID, doc.HashedDocumentName, doc.UploadTimestamp, doc.LastModified).
		WillReturnRows(rows)

	// Execute the method being tested
	err := repo.Create(context.Background(), doc)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(1), doc.ID) // ID should be set from RETURNING clause
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
	mock.ExpectQuery("INSERT INTO documents").
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
	mock.ExpectQuery("SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified FROM documents WHERE document_id = \\$1").
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
	mock.ExpectQuery("SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified FROM documents WHERE document_id = \\$1").
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
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)
	page := 1
	pageSize := 10
	offset := (page - 1) * pageSize
	now := time.Now()
	totalCount := 15

	// Setup for count query
	countRows := sqlmock.NewRows([]string{"count"}).AddRow(totalCount)
	mock.ExpectQuery("SELECT COUNT\\(\\*\\) FROM documents WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnRows(countRows)

	// Setup for main query
	docs := []*models.Document{
		{
			ID:                 1,
			UserID:             userID,
			HashedDocumentName: "doc1",
			UploadTimestamp:    now,
			LastModified:       now,
		},
		{
			ID:                 2,
			UserID:             userID,
			HashedDocumentName: "doc2",
			UploadTimestamp:    now.Add(-time.Hour),
			LastModified:       now.Add(-time.Hour),
		},
	}

	rows := sqlmock.NewRows([]string{"document_id", "user_id", "hashed_document_name", "upload_timestamp", "last_modified"})
	for _, doc := range docs {
		rows.AddRow(doc.ID, doc.UserID, doc.HashedDocumentName, doc.UploadTimestamp, doc.LastModified)
	}

	// Expected query with pagination parameters
	mock.ExpectQuery("SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified FROM documents WHERE user_id = \\$1 ORDER BY upload_timestamp DESC LIMIT \\$2 OFFSET \\$3").
		WithArgs(userID, pageSize, offset).
		WillReturnRows(rows)

	// Execute the method being tested
	results, count, err := repo.GetByUserID(context.Background(), userID, page, pageSize)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, totalCount, count)
	assert.Len(t, results, 2)
	assert.Equal(t, docs[0].ID, results[0].ID)
	assert.Equal(t, docs[1].ID, results[1].ID)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_Update(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	doc := &models.Document{
		ID:                 1,
		UserID:             100,
		HashedDocumentName: "hashed_name",
		UploadTimestamp:    now.Add(-time.Hour),
		LastModified:       now,
	}

	// Expected query with placeholders
	mock.ExpectExec("UPDATE documents SET last_modified = \\$1 WHERE document_id = \\$2").
		WithArgs(sqlmock.AnyArg(), doc.ID).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.Update(context.Background(), doc)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_Update_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	doc := &models.Document{
		ID:                 999,
		UserID:             100,
		HashedDocumentName: "hashed_name",
		UploadTimestamp:    now.Add(-time.Hour),
		LastModified:       now,
	}

	// Expected query with placeholders, but no rows affected
	mock.ExpectExec("UPDATE documents SET last_modified = \\$1 WHERE document_id = \\$2").
		WithArgs(sqlmock.AnyArg(), doc.ID).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Update(context.Background(), doc)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_Delete(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Set up transaction expectations
	mock.ExpectBegin()
	mock.ExpectExec("DELETE FROM detected_entities WHERE document_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 3)) // 3 entities deleted
	mock.ExpectExec("DELETE FROM documents WHERE document_id = \\$1").
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
	mock.ExpectExec("DELETE FROM detected_entities WHERE document_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0)) // No entities found
	mock.ExpectExec("DELETE FROM documents WHERE document_id = \\$1").
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
	mock.ExpectQuery("SELECT document_id FROM documents WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnRows(rows)

	// Then delete entities for each document
	for _, id := range docIDs {
		mock.ExpectExec("DELETE FROM detected_entities WHERE document_id = \\$1").
			WithArgs(id).
			WillReturnResult(sqlmock.NewResult(0, 2)) // 2 entities per document
	}

	// Finally delete all documents
	mock.ExpectExec("DELETE FROM documents WHERE user_id = \\$1").
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

	// Setup for PostgreSQL RETURNING clause
	rows := sqlmock.NewRows([]string{"entity_id"}).AddRow(100)

	// Expected query with placeholders
	mock.ExpectQuery("INSERT INTO detected_entities").
		WithArgs(entity.DocumentID, entity.MethodID, entity.EntityName, schemaJSON, entity.DetectedTimestamp).
		WillReturnRows(rows)

	// Execute the method being tested
	err := repo.AddDetectedEntity(context.Background(), entity)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(100), entity.ID) // ID should be set from RETURNING clause
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_DeleteDetectedEntity(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	entityID := int64(100)

	// Expected query with placeholder for entity ID
	mock.ExpectExec("DELETE FROM detected_entities WHERE entity_id = \\$1").
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
	mock.ExpectExec("DELETE FROM detected_entities WHERE entity_id = \\$1").
		WithArgs(entityID).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.DeleteDetectedEntity(context.Background(), entityID)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetDocumentSummary(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	documentID := int64(1)
	now := time.Now()
	summary := &models.DocumentSummary{
		ID:              documentID,
		HashedName:      "hashed_document_name",
		UploadTimestamp: now.Add(-time.Hour),
		LastModified:    now,
		EntityCount:     5,
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"document_id", "hashed_document_name", "upload_timestamp", "last_modified", "entity_count"}).
		AddRow(summary.ID, summary.HashedName, summary.UploadTimestamp, summary.LastModified, summary.EntityCount)

	// Expected query with placeholder for document ID
	mock.ExpectQuery("SELECT d\\.document_id, d\\.hashed_document_name, d\\.upload_timestamp, d\\.last_modified, COUNT\\(de\\.entity_id\\) AS entity_count FROM documents d LEFT JOIN detected_entities de ON d\\.document_id = de\\.document_id WHERE d\\.document_id = \\$1 GROUP BY d\\.document_id").
		WithArgs(documentID).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetDocumentSummary(context.Background(), documentID)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, summary.ID, result.ID)
	assert.Equal(t, summary.HashedName, result.HashedName)
	assert.WithinDuration(t, summary.UploadTimestamp, result.UploadTimestamp, time.Second)
	assert.WithinDuration(t, summary.LastModified, result.LastModified, time.Second)
	assert.Equal(t, summary.EntityCount, result.EntityCount)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetDocumentSummary_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	documentID := int64(999)

	// Mock database response - no rows
	mock.ExpectQuery("SELECT d\\.document_id, d\\.hashed_document_name, d\\.upload_timestamp, d\\.last_modified, COUNT\\(de\\.entity_id\\) AS entity_count FROM documents d LEFT JOIN detected_entities de ON d\\.document_id = de\\.document_id WHERE d\\.document_id = \\$1 GROUP BY d\\.document_id").
		WithArgs(documentID).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetDocumentSummary(context.Background(), documentID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}
