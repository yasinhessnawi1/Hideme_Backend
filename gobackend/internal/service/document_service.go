package service

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
	"os"

	"errors"
	"github.com/rs/zerolog/log"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
)

// Define custom error types
var (
	ErrDocumentNotFound  = errors.New("document not found")
	ErrInvalidDocumentID = errors.New("invalid document ID")
)

// DocumentService provides operations for managing documents.
type DocumentService struct {
	docRepo repository.DocumentRepository
}

// NewDocumentService creates a new DocumentService.
func NewDocumentService(docRepo repository.DocumentRepository) *DocumentService {
	return &DocumentService{docRepo: docRepo}
}

// ListDocuments retrieves documents for a user with pagination.
func (s *DocumentService) ListDocuments(userID int64, page, pageSize int) ([]*models.Document, int, error) {
	docs, total, err := s.docRepo.GetByUserID(context.Background(), userID, page, pageSize)
	if err != nil {
		return nil, 0, err
	}

	// Decrypt document names for display
	encryptionKey := []byte(os.Getenv("API_KEY_ENCRYPTION_KEY"))
	for _, doc := range docs {
		originalFilename, err := doc.DecryptDocumentName(encryptionKey)
		if err != nil {
			return nil, 0, fmt.Errorf("failed to decrypt document name: %w", err)
		}
		doc.HashedDocumentName = originalFilename
	}

	return docs, total, nil
}

// UploadDocument uploads a new document for a user.
func (s *DocumentService) UploadDocument(userID int64, filename string, redactionSchema models.RedactionMapping) (*models.Document, error) {
	// Convert redactionSchema to JSON
	redactionSchemaJSON, err := json.Marshal(redactionSchema)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal redaction schema: %w", err)
	}

	// Log the redaction schema
	log.Info().RawJSON("redaction_schema", redactionSchemaJSON).Msg("Processing redaction schema")

	doc := models.NewDocument(userID, filename, []byte(os.Getenv("API_KEY_ENCRYPTION_KEY")))
	doc.RedactionSchema = string(redactionSchemaJSON) // Store as JSON string

	if err := s.docRepo.Create(context.Background(), doc); err != nil {
		return nil, err
	}

	// Decrypt the document name before returning
	originalFilename, err := doc.DecryptDocumentName([]byte(os.Getenv("API_KEY_ENCRYPTION_KEY")))
	if err != nil {
		return nil, fmt.Errorf("failed to decrypt document name: %w", err)
	}
	doc.HashedDocumentName = originalFilename

	return doc, nil
}

// GetDocumentByID retrieves a document by its ID.
func (s *DocumentService) GetDocumentByID(id int64) (*models.Document, error) {
	doc, err := s.docRepo.GetByID(context.Background(), id)
	if err != nil {
		if errors.Is(err, utils.ErrNotFound) {
			return nil, ErrDocumentNotFound
		}
		return nil, err
	}

	// Check if redaction_schema is empty
	if doc.RedactionSchema == "" {
		doc.RedactionSchema = "{}" // Set to empty JSON object if empty
	}

	// Unmarshal the redaction_schema JSON string into a RedactionMapping struct
	var redactionMapping models.RedactionMapping
	if err := json.Unmarshal([]byte(doc.RedactionSchema), &redactionMapping); err != nil {
		return nil, fmt.Errorf("failed to unmarshal redaction schema: %w", err)
	}

	// Make sure the document name is decrypted
	originalFilename, err := doc.DecryptDocumentName([]byte(os.Getenv("API_KEY_ENCRYPTION_KEY")))
	if err != nil {
		return nil, fmt.Errorf("failed to decrypt document name: %w", err)
	}
	doc.HashedDocumentName = originalFilename

	// Return the document with the computed entity_count
	return &models.Document{
		ID:                 doc.ID,
		UserID:             doc.UserID,
		HashedDocumentName: doc.HashedDocumentName,
		UploadTimestamp:    doc.UploadTimestamp,
		LastModified:       doc.LastModified,
		RedactionSchema:    doc.RedactionSchema, // Keep as string for storage
	}, nil
}

// DeleteDocumentByID deletes a document by its ID.
func (s *DocumentService) DeleteDocumentByID(id int64) error {
	err := s.docRepo.Delete(context.Background(), id)
	if err != nil {
		if errors.Is(err, utils.ErrNotFound) {
			return ErrDocumentNotFound
		}
		return err
	}
	return nil
}

// GetDocumentSummary retrieves a summary of a document.
func (s *DocumentService) GetDocumentSummary(id int64) (*models.DocumentSummary, error) {
	summary, err := s.docRepo.GetDocumentSummary(context.Background(), id)
	if err != nil {
		return nil, err
	}

	// The HashedName should already be decrypted by the repository
	// Double-check to ensure it's using the original filename
	encryptionKey := []byte(os.Getenv("API_KEY_ENCRYPTION_KEY"))
	doc, err := s.docRepo.GetByID(context.Background(), id)
	if err != nil {
		return nil, err
	}

	originalFilename, err := doc.DecryptDocumentName(encryptionKey)
	if err != nil {
		return nil, fmt.Errorf("failed to decrypt document name: %w", err)
	}
	summary.HashedName = originalFilename

	return summary, nil
}
