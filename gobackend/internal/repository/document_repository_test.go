package repository_test

import (
	"context"
	"database/sql"
	"errors"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
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

	// Create a test encryption key (32 bytes for AES-256)
	encryptionKey := []byte("test-encryption-key-for-unit-tests")

	// Create a new repository with the mocked database and encryption key
	repo := repository.NewDocumentRepository(dbPool, encryptionKey).(*repository.PostgresDocumentRepository)

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
		RedactionSchema:    "", // Add this field
	}

	// Setup for PostgreSQL RETURNING clause
	rows := sqlmock.NewRows([]string{"document_id"}).AddRow(1)

	// Expected query with placeholders for the arguments - now including redaction_schema
	mock.ExpectQuery("INSERT INTO documents").
		WithArgs(doc.UserID, sqlmock.AnyArg(), doc.UploadTimestamp, doc.LastModified, doc.RedactionSchema).
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
		RedactionSchema:    "", // Add this field
	}

	// Mock database error - now expecting 5 arguments including redaction_schema
	mock.ExpectQuery("INSERT INTO documents").
		WithArgs(doc.UserID, sqlmock.AnyArg(), doc.UploadTimestamp, doc.LastModified, doc.RedactionSchema).
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

	// Use a proper 32-byte encryption key
	encryptionKey := []byte("test-encryption-key-for-unit-tests")
	if len(encryptionKey) < 32 {
		// Pad the key to 32 bytes if needed
		padded := make([]byte, 32)
		copy(padded, encryptionKey)
		encryptionKey = padded
	}

	// Create an encrypted document name
	originalFilename := "test_document.pdf"
	encryptedName, err := utils.EncryptKey(originalFilename, encryptionKey)
	require.NoError(t, err, "Failed to encrypt test filename")

	doc := &models.Document{
		ID:                 id,
		UserID:             100,
		HashedDocumentName: encryptedName, // Use the properly encrypted name
		UploadTimestamp:    now,
		LastModified:       now,
		RedactionSchema:    "{}", // Add this field
	}

	// Set up query result - now including redaction_schema
	rows := sqlmock.NewRows([]string{"document_id", "user_id", "hashed_document_name", "upload_timestamp", "last_modified", "redaction_schema"}).
		AddRow(doc.ID, doc.UserID, doc.HashedDocumentName, doc.UploadTimestamp, doc.LastModified, doc.RedactionSchema)

	// Expected query with placeholder for the ID - now selecting redaction_schema
	mock.ExpectQuery("SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified, redaction_schema FROM documents WHERE document_id = \\$1").
		WithArgs(id).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.NotNil(t, result, "Result should not be nil")
	assert.Equal(t, doc.ID, result.ID)
	assert.Equal(t, doc.UserID, result.UserID)
	// The HashedDocumentName should now contain the decrypted value
	assert.Equal(t, originalFilename, result.HashedDocumentName)
	assert.WithinDuration(t, doc.UploadTimestamp, result.UploadTimestamp, time.Second)
	assert.WithinDuration(t, doc.LastModified, result.LastModified, time.Second)
	assert.NoError(t, mock.ExpectationsWereMet())
}

// TestDocumentRepository_GetByID_NotFound tests the GetByID method when a document is not found
func TestDocumentRepository_GetByID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Mock database response - empty result
	mock.ExpectQuery("SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified, redaction_schema FROM documents WHERE document_id = \\$1").
		WithArgs(id).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

// TestDocumentRepository_GetByID_OtherError tests the GetByID method when a database error occurs
func TestDocumentRepository_GetByID_OtherError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Mock database error (not ErrNoRows)
	mock.ExpectQuery("SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified, redaction_schema FROM documents WHERE document_id = \\$1").
		WithArgs(id).
		WillReturnError(errors.New("database connection error"))

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.Contains(t, err.Error(), "failed to get document by ID")
	assert.NoError(t, mock.ExpectationsWereMet())
}

// TestDocumentRepository_GetByUserID tests the GetByUserID method
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

	// Create a proper 32-byte encryption key
	encryptionKey := []byte("test-encryption-key-for-unit-tests")
	if len(encryptionKey) < 32 {
		padded := make([]byte, 32)
		copy(padded, encryptionKey)
		encryptionKey = padded
	}

	// Create encrypted document names
	encryptedName1, err := utils.EncryptKey("doc1", encryptionKey)
	require.NoError(t, err)
	encryptedName2, err := utils.EncryptKey("doc2", encryptionKey)
	require.NoError(t, err)

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
			HashedDocumentName: encryptedName1,
			UploadTimestamp:    now,
			LastModified:       now,
		},
		{
			ID:                 2,
			UserID:             userID,
			HashedDocumentName: encryptedName2,
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
	// The decrypted names should match the original values
	assert.Equal(t, "doc1", results[0].HashedDocumentName)
	assert.Equal(t, "doc2", results[1].HashedDocumentName)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetByUserID_CountError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)
	page := 1
	pageSize := 10

	// Mock count query error
	mock.ExpectQuery("SELECT COUNT\\(\\*\\) FROM documents WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnError(errors.New("count query error"))

	// Execute the method being tested
	results, count, err := repo.GetByUserID(context.Background(), userID, page, pageSize)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to count documents")
	assert.Equal(t, 0, count)
	assert.Nil(t, results)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetByUserID_QueryError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)
	page := 1
	pageSize := 10
	offset := (page - 1) * pageSize
	totalCount := 15

	// Setup for count query
	countRows := sqlmock.NewRows([]string{"count"}).AddRow(totalCount)
	mock.ExpectQuery("SELECT COUNT\\(\\*\\) FROM documents WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnRows(countRows)

	// Mock main query error
	mock.ExpectQuery("SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified FROM documents WHERE user_id = \\$1 ORDER BY upload_timestamp DESC LIMIT \\$2 OFFSET \\$3").
		WithArgs(userID, pageSize, offset).
		WillReturnError(errors.New("query error"))

	// Execute the method being tested
	results, count, err := repo.GetByUserID(context.Background(), userID, page, pageSize)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get documents by user ID")
	assert.Equal(t, 0, count)
	assert.Nil(t, results)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetByUserID_ScanError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)
	page := 1
	pageSize := 10
	offset := (page - 1) * pageSize
	totalCount := 15

	// Setup for count query
	countRows := sqlmock.NewRows([]string{"count"}).AddRow(totalCount)
	mock.ExpectQuery("SELECT COUNT\\(\\*\\) FROM documents WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnRows(countRows)

	// Setup for main query with invalid data to cause scan error
	rows := sqlmock.NewRows([]string{"document_id", "user_id", "hashed_document_name", "upload_timestamp", "last_modified"}).
		AddRow("invalid_id", userID, "doc1", time.Now(), time.Now()) // invalid_id will cause scan error

	mock.ExpectQuery("SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified FROM documents WHERE user_id = \\$1 ORDER BY upload_timestamp DESC LIMIT \\$2 OFFSET \\$3").
		WithArgs(userID, pageSize, offset).
		WillReturnRows(rows)

	// Execute the method being tested
	results, count, err := repo.GetByUserID(context.Background(), userID, page, pageSize)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to scan document row")
	assert.Equal(t, 0, count)
	assert.Nil(t, results)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetByUserID_RowsError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)
	page := 1
	pageSize := 10
	offset := (page - 1) * pageSize
	totalCount := 15

	// Setup for count query
	countRows := sqlmock.NewRows([]string{"count"}).AddRow(totalCount)
	mock.ExpectQuery("SELECT COUNT\\(\\*\\) FROM documents WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnRows(countRows)

	// Setup for main query with row error
	rows := sqlmock.NewRows([]string{"document_id", "user_id", "hashed_document_name", "upload_timestamp", "last_modified"}).
		AddRow(1, userID, "doc1", time.Now(), time.Now()).
		RowError(0, errors.New("row error"))

	mock.ExpectQuery("SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified FROM documents WHERE user_id = \\$1 ORDER BY upload_timestamp DESC LIMIT \\$2 OFFSET \\$3").
		WithArgs(userID, pageSize, offset).
		WillReturnRows(rows)

	// Execute the method being tested
	results, count, err := repo.GetByUserID(context.Background(), userID, page, pageSize)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "error iterating document rows")
	assert.Equal(t, 0, count)
	assert.Nil(t, results)
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

func TestDocumentRepository_Update_Error(t *testing.T) {
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

	// Mock database error
	mock.ExpectExec("UPDATE documents SET last_modified = \\$1 WHERE document_id = \\$2").
		WithArgs(sqlmock.AnyArg(), doc.ID).
		WillReturnError(errors.New("database error"))

	// Execute the method being tested
	err := repo.Update(context.Background(), doc)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to update document")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_Update_RowsAffectedError(t *testing.T) {
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

	// Create a custom result that returns an error for RowsAffected()
	result := sqlmock.NewErrorResult(errors.New("rows affected error"))

	// Mock the update with error result
	mock.ExpectExec("UPDATE documents SET last_modified = \\$1 WHERE document_id = \\$2").
		WithArgs(sqlmock.AnyArg(), doc.ID).
		WillReturnResult(result)

	// Execute the method being tested
	err := repo.Update(context.Background(), doc)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get rows affected")
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

func TestDocumentRepository_Delete_EntitiesError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Set up transaction expectations with error in entities deletion
	mock.ExpectBegin()
	mock.ExpectExec("DELETE FROM detected_entities WHERE document_id = \\$1").
		WithArgs(id).
		WillReturnError(errors.New("entities deletion error"))
	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to delete detected entities")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_Delete_DocumentError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Set up transaction expectations with error in document deletion
	mock.ExpectBegin()
	mock.ExpectExec("DELETE FROM detected_entities WHERE document_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 3))
	mock.ExpectExec("DELETE FROM documents WHERE document_id = \\$1").
		WithArgs(id).
		WillReturnError(errors.New("document deletion error"))
	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to delete document")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_Delete_RowsAffectedError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Set up transaction expectations with rows affected error
	mock.ExpectBegin()
	mock.ExpectExec("DELETE FROM detected_entities WHERE document_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 3))

	// Create a custom result that returns an error for RowsAffected()
	result := sqlmock.NewErrorResult(errors.New("rows affected error"))

	mock.ExpectExec("DELETE FROM documents WHERE document_id = \\$1").
		WithArgs(id).
		WillReturnResult(result)
	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get rows affected")
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

func TestDocumentRepository_DeleteByUserID_GetDocumentsError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Set up transaction expectations with error in getting document IDs
	mock.ExpectBegin()
	mock.ExpectQuery("SELECT document_id FROM documents WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnError(errors.New("get documents error"))
	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get document IDs")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_DeleteByUserID_ScanError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Set up transaction expectations with scan error
	mock.ExpectBegin()

	// Create rows with invalid data to cause scan error
	rows := sqlmock.NewRows([]string{"document_id"}).
		AddRow("invalid_id") // String instead of int64 will cause scan error

	mock.ExpectQuery("SELECT document_id FROM documents WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnRows(rows)
	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to scan document ID")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_DeleteByUserID_RowsError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Set up transaction expectations with rows error
	mock.ExpectBegin()

	// Create rows with an error
	rows := sqlmock.NewRows([]string{"document_id"}).
		AddRow(1).
		RowError(0, errors.New("row iteration error"))

	mock.ExpectQuery("SELECT document_id FROM documents WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnRows(rows)
	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "error iterating document ID rows")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_DeleteByUserID_DeleteEntitiesError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)
	docIDs := []int64{1, 2}

	// Set up transaction expectations with delete entities error
	mock.ExpectBegin()

	// First get document IDs
	rows := sqlmock.NewRows([]string{"document_id"})
	for _, id := range docIDs {
		rows.AddRow(id)
	}
	mock.ExpectQuery("SELECT document_id FROM documents WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnRows(rows)

	// Error on first entity deletion
	mock.ExpectExec("DELETE FROM detected_entities WHERE document_id = \\$1").
		WithArgs(docIDs[0]).
		WillReturnError(errors.New("delete entities error"))
	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to delete detected entities")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_DeleteByUserID_DeleteDocumentsError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)
	docIDs := []int64{1, 2}

	// Set up transaction expectations with delete documents error
	mock.ExpectBegin()

	// First get document IDs
	rows := sqlmock.NewRows([]string{"document_id"})
	for _, id := range docIDs {
		rows.AddRow(id)
	}
	mock.ExpectQuery("SELECT document_id FROM documents WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnRows(rows)

	// Delete entities successfully for each document
	for _, id := range docIDs {
		mock.ExpectExec("DELETE FROM detected_entities WHERE document_id = \\$1").
			WithArgs(id).
			WillReturnResult(sqlmock.NewResult(0, 2))
	}

	// Error on document deletion
	mock.ExpectExec("DELETE FROM documents WHERE user_id = \\$1").
		WithArgs(userID).
		WillReturnError(errors.New("delete documents error"))
	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to delete documents by user ID")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetDetectedEntities(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	documentID := int64(1)
	now := time.Now()
	entities := []*models.DetectedEntityWithMethod{
		{
			DetectedEntity: models.DetectedEntity{
				ID:                1,
				DocumentID:        documentID,
				MethodID:          1,
				EntityName:        "Credit Card",
				RedactionSchema:   models.RedactionSchema{Page: 1, StartX: 10, StartY: 20, EndX: 30, EndY: 40, RedactionMethod: "blackout"},
				DetectedTimestamp: now,
			},
			MethodName:     "ML Model",
			HighlightColor: "#FF0000",
		},
		{
			DetectedEntity: models.DetectedEntity{
				ID:                2,
				DocumentID:        documentID,
				MethodID:          2,
				EntityName:        "SSN",
				RedactionSchema:   models.RedactionSchema{Page: 1, StartX: 50, StartY: 60, EndX: 70, EndY: 80, RedactionMethod: "mask"},
				DetectedTimestamp: now.Add(-time.Hour),
			},
			MethodName:     "Regex",
			HighlightColor: "#00FF00",
		},
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"entity_id", "document_id", "method_id", "entity_name", "redaction_schema", "detected_timestamp", "method_name", "highlight_color"})
	for _, entity := range entities {
		schemaJSON, _ := entity.RedactionSchema.Value()
		rows.AddRow(entity.ID, entity.DocumentID, entity.MethodID, entity.EntityName, schemaJSON, entity.DetectedTimestamp, entity.MethodName, entity.HighlightColor)
	}

	// Expected query with placeholder for document ID
	mock.ExpectQuery("SELECT de\\.entity_id, de\\.document_id, de\\.method_id, de\\.entity_name, de\\.redaction_schema, de\\.detected_timestamp, dm\\.method_name, dm\\.highlight_color FROM detected_entities de JOIN detection_methods dm ON de\\.method_id = dm\\.method_id WHERE de\\.document_id = \\$1 ORDER BY de\\.detected_timestamp DESC").
		WithArgs(documentID).
		WillReturnRows(rows)

	// Execute the method being tested
	results, err := repo.GetDetectedEntities(context.Background(), documentID)

	// Assert the results
	assert.NoError(t, err)
	assert.Len(t, results, 2)
	assert.Equal(t, entities[0].ID, results[0].ID)
	assert.Equal(t, entities[0].EntityName, results[0].EntityName)
	assert.Equal(t, entities[0].MethodName, results[0].MethodName)
	assert.Equal(t, entities[1].ID, results[1].ID)
	assert.Equal(t, entities[1].EntityName, results[1].EntityName)
	assert.Equal(t, entities[1].MethodName, results[1].MethodName)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetDetectedEntities_QueryError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	documentID := int64(1)

	// Mock query error
	mock.ExpectQuery("SELECT de\\.entity_id, de\\.document_id, de\\.method_id, de\\.entity_name, de\\.redaction_schema, de\\.detected_timestamp, dm\\.method_name, dm\\.highlight_color FROM detected_entities de JOIN detection_methods dm ON de\\.method_id = dm\\.method_id WHERE de\\.document_id = \\$1 ORDER BY de\\.detected_timestamp DESC").
		WithArgs(documentID).
		WillReturnError(errors.New("query error"))

	// Execute the method being tested
	results, err := repo.GetDetectedEntities(context.Background(), documentID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, results)
	assert.Contains(t, err.Error(), "failed to get detected entities")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetDetectedEntities_ScanError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	documentID := int64(1)

	// Set up query result with invalid data to cause scan error
	rows := sqlmock.NewRows([]string{"entity_id", "document_id", "method_id", "entity_name", "redaction_schema", "detected_timestamp", "method_name", "highlight_color"}).
		AddRow("invalid_id", documentID, 1, "Credit Card", "{}", time.Now(), "ML Model", "#FF0000") // invalid_id will cause scan error

	mock.ExpectQuery("SELECT de\\.entity_id, de\\.document_id, de\\.method_id, de\\.entity_name, de\\.redaction_schema, de\\.detected_timestamp, dm\\.method_name, dm\\.highlight_color FROM detected_entities de JOIN detection_methods dm ON de\\.method_id = dm\\.method_id WHERE de\\.document_id = \\$1 ORDER BY de\\.detected_timestamp DESC").
		WithArgs(documentID).
		WillReturnRows(rows)

	// Execute the method being tested
	results, err := repo.GetDetectedEntities(context.Background(), documentID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, results)
	assert.Contains(t, err.Error(), "failed to scan detected entity row")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_GetDetectedEntities_RowsError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	documentID := int64(1)

	// Set up query result with row error
	rows := sqlmock.NewRows([]string{"entity_id", "document_id", "method_id", "entity_name", "redaction_schema", "detected_timestamp", "method_name", "highlight_color"}).
		AddRow(1, documentID, 1, "Credit Card", "{}", time.Now(), "ML Model", "#FF0000").
		RowError(0, errors.New("row iteration error"))

	mock.ExpectQuery("SELECT de\\.entity_id, de\\.document_id, de\\.method_id, de\\.entity_name, de\\.redaction_schema, de\\.detected_timestamp, dm\\.method_name, dm\\.highlight_color FROM detected_entities de JOIN detection_methods dm ON de\\.method_id = dm\\.method_id WHERE de\\.document_id = \\$1 ORDER BY de\\.detected_timestamp DESC").
		WithArgs(documentID).
		WillReturnRows(rows)

	// Execute the method being tested
	results, err := repo.GetDetectedEntities(context.Background(), documentID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, results)
	assert.Contains(t, err.Error(), "error iterating detected entity rows")
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

	entity := &models.DetectedEntity{
		DocumentID:        1,
		MethodID:          1,
		EntityName:        "Credit Card",
		RedactionSchema:   schema,
		DetectedTimestamp: now,
	}

	// Setup for PostgreSQL RETURNING clause
	rows := sqlmock.NewRows([]string{"entity_id"}).AddRow(100)

	// Expected query with placeholders - use AnyArg for the encrypted schema
	mock.ExpectQuery("INSERT INTO detected_entities").
		WithArgs(entity.DocumentID, entity.MethodID, entity.EntityName, sqlmock.AnyArg(), entity.DetectedTimestamp).
		WillReturnRows(rows)

	// Execute the method being tested
	err := repo.AddDetectedEntity(context.Background(), entity)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(100), entity.ID) // ID should be set from RETURNING clause
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_AddDetectedEntity_Error(t *testing.T) {
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

	entity := &models.DetectedEntity{
		DocumentID:        1,
		MethodID:          1,
		EntityName:        "Credit Card",
		RedactionSchema:   schema,
		DetectedTimestamp: now,
	}

	// Mock query error - use AnyArg for the encrypted schema
	mock.ExpectQuery("INSERT INTO detected_entities").
		WithArgs(entity.DocumentID, entity.MethodID, entity.EntityName, sqlmock.AnyArg(), entity.DetectedTimestamp).
		WillReturnError(errors.New("insert error"))

	// Execute the method being tested
	err := repo.AddDetectedEntity(context.Background(), entity)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to create detected entity")
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

func TestDocumentRepository_DeleteDetectedEntity_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	entityID := int64(100)

	// Mock query error
	mock.ExpectExec("DELETE FROM detected_entities WHERE entity_id = \\$1").
		WithArgs(entityID).
		WillReturnError(errors.New("delete error"))

	// Execute the method being tested
	err := repo.DeleteDetectedEntity(context.Background(), entityID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to delete detected entity")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestDocumentRepository_DeleteDetectedEntity_RowsAffectedError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	entityID := int64(100)

	// Create a custom result that returns an error for RowsAffected()
	result := sqlmock.NewErrorResult(errors.New("rows affected error"))

	// Mock the deletion with error result
	mock.ExpectExec("DELETE FROM detected_entities WHERE entity_id = \\$1").
		WithArgs(entityID).
		WillReturnResult(result)

	// Execute the method being tested
	err := repo.DeleteDetectedEntity(context.Background(), entityID)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get rows affected")
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

	// Create a proper 32-byte encryption key
	encryptionKey := []byte("test-encryption-key-for-unit-tests")
	if len(encryptionKey) < 32 {
		padded := make([]byte, 32)
		copy(padded, encryptionKey)
		encryptionKey = padded
	}

	// Create an encrypted document name
	originalFilename := "test_document.pdf"
	encryptedName, err := utils.EncryptKey(originalFilename, encryptionKey)
	require.NoError(t, err, "Failed to encrypt test filename")

	summary := &models.DocumentSummary{
		ID:              documentID,
		HashedName:      encryptedName, // Use the encrypted name
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
	assert.NotNil(t, result, "Result should not be nil")
	assert.Equal(t, summary.ID, result.ID)
	assert.Equal(t, originalFilename, result.HashedName) // Should be decrypted
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

func TestDocumentRepository_GetDocumentSummary_OtherError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupDocumentRepositoryTest(t)
	defer cleanup()

	// Set up test data
	documentID := int64(1)

	// Mock database error (not ErrNoRows)
	mock.ExpectQuery("SELECT d\\.document_id, d\\.hashed_document_name, d\\.upload_timestamp, d\\.last_modified, COUNT\\(de\\.entity_id\\) AS entity_count FROM documents d LEFT JOIN detected_entities de ON d\\.document_id = de\\.document_id WHERE d\\.document_id = \\$1 GROUP BY d\\.document_id").
		WithArgs(documentID).
		WillReturnError(errors.New("database error"))

	// Execute the method being tested
	result, err := repo.GetDocumentSummary(context.Background(), documentID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.Contains(t, err.Error(), "failed to get document summary")
	assert.NoError(t, mock.ExpectationsWereMet())
}
