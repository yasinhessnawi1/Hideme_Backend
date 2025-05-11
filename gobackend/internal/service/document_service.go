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

	encryptionKey := []byte(os.Getenv("API_KEY_ENCRYPTION_KEY"))
	for _, doc := range docs {
		// Decrypt document names for display
		originalFilename, err := doc.DecryptDocumentName(encryptionKey)
		if err != nil {
			return nil, 0, fmt.Errorf("failed to decrypt document name: %w", err)
		}
		doc.HashedDocumentName = originalFilename

		// Decrypt redaction schema if it exists
		if doc.RedactionSchema != "" && doc.RedactionSchema != "{}" {
			decryptedSchema, err := doc.DecryptRedactionSchema(encryptionKey)
			if err != nil {
				return nil, 0, fmt.Errorf("failed to decrypt redaction schema: %w", err)
			}
			doc.RedactionSchema = decryptedSchema
		}
	}

	return docs, total, nil
}

func (s *DocumentService) CalculateEntityCount(redactionSchema string) int {
	if redactionSchema == "" || redactionSchema == "{}" {
		return 0
	}

	var redactionMapping models.RedactionMapping
	if err := json.Unmarshal([]byte(redactionSchema), &redactionMapping); err != nil {
		return 0
	}

	count := 0
	for _, page := range redactionMapping.Pages {
		count += len(page.Sensitive)
	}

	return count
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

	encryptionKey := []byte(os.Getenv("API_KEY_ENCRYPTION_KEY"))
	doc := models.NewDocument(userID, filename, encryptionKey)

	// Encrypt the redaction schema before storing
	if err := doc.EncryptRedactionSchema(string(redactionSchemaJSON), encryptionKey); err != nil {
		return nil, fmt.Errorf("failed to encrypt redaction schema: %w", err)
	}

	if err := s.docRepo.Create(context.Background(), doc); err != nil {
		return nil, err
	}

	// Decrypt the document name before returning
	originalFilename, err := doc.DecryptDocumentName(encryptionKey)
	if err != nil {
		return nil, fmt.Errorf("failed to decrypt document name: %w", err)
	}
	doc.HashedDocumentName = originalFilename

	// We'll return the unencrypted schema in the response
	doc.RedactionSchema = string(redactionSchemaJSON)

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

	encryptionKey := []byte(os.Getenv("API_KEY_ENCRYPTION_KEY"))

	// Check if redaction_schema is empty
	if doc.RedactionSchema == "" {
		doc.RedactionSchema = "{}" // Set to empty JSON object if empty
	} else {
		// Decrypt the redaction schema
		decryptedSchema, err := doc.DecryptRedactionSchema(encryptionKey)
		if err != nil {
			return nil, fmt.Errorf("failed to decrypt redaction schema: %w", err)
		}
		doc.RedactionSchema = decryptedSchema
	}

	// Verify the decrypted schema is valid JSON
	var redactionMapping models.RedactionMapping
	if err := json.Unmarshal([]byte(doc.RedactionSchema), &redactionMapping); err != nil {
		return nil, fmt.Errorf("failed to unmarshal redaction schema: %w", err)
	}

	// Make sure the document name is decrypted
	originalFilename, err := doc.DecryptDocumentName(encryptionKey)
	if err != nil {
		return nil, fmt.Errorf("failed to decrypt document name: %w", err)
	}
	doc.HashedDocumentName = originalFilename

	// Return the document with the decrypted data
	return &models.Document{
		ID:                 doc.ID,
		UserID:             doc.UserID,
		HashedDocumentName: doc.HashedDocumentName,
		UploadTimestamp:    doc.UploadTimestamp,
		LastModified:       doc.LastModified,
		RedactionSchema:    doc.RedactionSchema, // Return the decrypted schema
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
