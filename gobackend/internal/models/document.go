package models

import (
	"crypto/sha256"
	"encoding/hex"
	"time"
)

// Document represents a document uploaded to the HideMe application for processing.
// To comply with GDPR and data minimization principles, it stores only document metadata
// and not the actual document content.
type Document struct {
	ID                 int64     `json:"id" db:"document_id"`
	UserID             int64     `json:"user_id" db:"user_id"`
	HashedDocumentName string    `json:"hashed_document_name" db:"hashed_document_name"`
	UploadTimestamp    time.Time `json:"upload_timestamp" db:"upload_timestamp"`
	LastModified       time.Time `json:"last_modified" db:"last_modified"`
}

// NewDocument creates a new Document instance with the given original filename and user ID.
// It generates a hashed version of the document name for privacy.
func NewDocument(userID int64, originalFilename string) *Document {
	now := time.Now()
	return &Document{
		UserID:             userID,
		HashedDocumentName: hashDocumentName(originalFilename),
		UploadTimestamp:    now,
		LastModified:       now,
	}
}

// TableName returns the database table name for the Document model.
func (d *Document) TableName() string {
	return "documents"
}

// hashDocumentName creates a SHA-256 hash of the original document name to protect
// potentially sensitive information in filenames.
func hashDocumentName(originalName string) string {
	hash := sha256.Sum256([]byte(originalName))
	return hex.EncodeToString(hash[:])
}

// UpdateLastModified updates the last modified timestamp to the current time.
func (d *Document) UpdateLastModified() {
	d.LastModified = time.Now()
}

// DocumentSummary represents a summary of document information returned to the client.
type DocumentSummary struct {
	ID              int64     `json:"id"`
	HashedName      string    `json:"hashed_name"`
	UploadTimestamp time.Time `json:"upload_timestamp"`
	LastModified    time.Time `json:"last_modified"`
	EntityCount     int       `json:"entity_count"`
}
