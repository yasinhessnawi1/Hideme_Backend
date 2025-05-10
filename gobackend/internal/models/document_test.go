package models_test

import (
	"crypto/sha256"
	"encoding/hex"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestDocument_TableName(t *testing.T) {
	// Create a test document
	document := &models.Document{
		ID:                 1,
		UserID:             100,
		HashedDocumentName: "hashedname123",
		UploadTimestamp:    time.Now(),
		LastModified:       time.Now(),
	}

	// Verify the table name
	tableName := document.TableName()
	assert.Equal(t, "documents", tableName, "TableName should return the correct database table name")
}

func TestNewDocument(t *testing.T) {
	// Test parameters
	userID := int64(100)
	originalFilename := "sensitive_document.pdf"

	// Expected hashed name
	hash := sha256.Sum256([]byte(originalFilename))
	expectedHashedName := hex.EncodeToString(hash[:])

	// Create a new document
	now := time.Now()
	document := models.NewDocument(userID, originalFilename, []byte("my-secret-key"))

	// Verify the document was created correctly
	assert.NotNil(t, document, "NewDocument should return a non-nil Document")
	assert.Equal(t, userID, document.UserID, "Document should have the provided user ID")
	assert.Equal(t, expectedHashedName, document.HashedDocumentName, "Document should have the correct hashed name")
	assert.WithinDuration(t, now, document.UploadTimestamp, time.Second, "UploadTimestamp should be set to current time")
	assert.WithinDuration(t, now, document.LastModified, time.Second, "LastModified should be set to current time")
	assert.Equal(t, int64(0), document.ID, "A new Document should have zero ID until saved to database")
}

func TestDocument_UpdateLastModified(t *testing.T) {
	// Create a test document with a fixed timestamp
	oldTime := time.Now().Add(-24 * time.Hour)
	document := &models.Document{
		ID:                 1,
		UserID:             100,
		HashedDocumentName: "hashedname123",
		UploadTimestamp:    oldTime,
		LastModified:       oldTime,
	}

	// Update the last modified timestamp
	now := time.Now()
	document.UpdateLastModified()

	// Verify the timestamp was updated
	assert.WithinDuration(t, now, document.LastModified, time.Second, "LastModified should be updated to current time")
	assert.Equal(t, oldTime, document.UploadTimestamp, "UploadTimestamp should remain unchanged")
}

func TestDocumentSummary(t *testing.T) {
	// Create a document summary
	now := time.Now()
	summary := &models.DocumentSummary{
		ID:              123,
		HashedName:      "hashedname456",
		UploadTimestamp: now,
		LastModified:    now.Add(time.Hour),
		EntityCount:     5,
	}

	// Verify the fields
	assert.Equal(t, int64(123), summary.ID)
	assert.Equal(t, "hashedname456", summary.HashedName)
	assert.Equal(t, now, summary.UploadTimestamp)
	assert.Equal(t, now.Add(time.Hour), summary.LastModified)
	assert.Equal(t, 5, summary.EntityCount)
}
