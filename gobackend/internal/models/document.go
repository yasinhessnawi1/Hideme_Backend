// Package models provides data structures and operations for the HideMe application.
// This file contains models related to document management and metadata handling.
package models

import (
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// Document represents a document uploaded to the HideMe application for processing.
// To comply with GDPR and data minimization principles, it stores only document metadata
// and not the actual document content. This approach reduces privacy risks while still
// allowing for necessary document management functionality.
type Document struct {
	// ID is the unique identifier for this document
	ID int64 `json:"id" db:"document_id"`

	// UserID references the owner of this document
	UserID int64 `json:"user_id" db:"user_id"`

	// HashedDocumentName stores a secure hash of the original filename
	// This preserves privacy while enabling document identification
	HashedDocumentName string `json:"hashed_document_name" db:"hashed_document_name"`

	// UploadTimestamp records when this document was initially uploaded
	UploadTimestamp time.Time `json:"upload_timestamp" db:"upload_timestamp"`

	// LastModified records when this document was last modified
	LastModified time.Time `json:"last_modified" db:"last_modified"`
}

// NewDocument creates a new Document instance with the given original filename and user ID.
// It encrypts the document name for privacy.
//
// Parameters:
//   - userID: The ID of the user who owns this document
//   - originalFilename: The original name of the uploaded file
//   - encryptionKey: The key to use for encryption (must be at least 32 bytes)
//
// Returns:
//   - A new Document pointer with initialized fields and timestamps
//
// The document's name is securely encrypted to comply with privacy principles.
// Both UploadTimestamp and LastModified are set to the current time.
func NewDocument(userID int64, originalFilename string, encryptionKey []byte) *Document {
	encryptedName, _ := utils.EncryptKey(originalFilename, encryptionKey) // ignore error for now, handle in repo
	now := time.Now()
	return &Document{
		UserID:             userID,
		HashedDocumentName: encryptedName,
		UploadTimestamp:    now,
		LastModified:       now,
	}
}

// TableName returns the database table name for the Document model.
// This method is used by ORM frameworks to determine where to persist this entity.
func (d *Document) TableName() string {
	return constants.TableDocuments
}

// DecryptDocumentName decrypts the encrypted document name using the provided key.
func (d *Document) DecryptDocumentName(encryptionKey []byte) (string, error) {
	return utils.DecryptKey(d.HashedDocumentName, encryptionKey)
}

// UpdateLastModified updates the last modified timestamp to the current time.
// This should be called whenever the document or its related entities are modified.
func (d *Document) UpdateLastModified() {
	d.LastModified = time.Now()
}

// DocumentSummary represents a summary of document information returned to the client.
// This provides essential metadata without exposing sensitive details.
type DocumentSummary struct {
	// ID is the unique identifier for this document
	ID int64 `json:"id"`

	// HashedName is the hashed version of the original filename
	HashedName string `json:"hashed_name"`

	// UploadTimestamp records when this document was initially uploaded
	UploadTimestamp time.Time `json:"upload_timestamp"`

	// LastModified records when this document was last modified
	LastModified time.Time `json:"last_modified"`

	// EntityCount indicates how many sensitive entities were detected in this document
	EntityCount int `json:"entity_count"`
}
