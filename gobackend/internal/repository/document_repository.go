// Package repository provides data access interfaces and implementations for the HideMe application.
// It follows the repository pattern to abstract database operations and provide a clean API
// for data persistence operations.
//
// This file implements the document repository, which manages processed documents and their
// detected sensitive entities. The repository enforces data minimization principles by
// storing only metadata about documents rather than actual document content.
package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// DocumentRepository defines methods for interacting with documents and their detected entities.
// It provides operations for document management including creation, retrieval, update,
// and deletion, as well as management of sensitive information detected within those documents.
type DocumentRepository interface {
	// Create adds a new document to the database.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - document: The document to store, with required fields populated
	//
	// Returns:
	//   - An error if creation fails
	//   - nil on successful creation
	//
	// The document ID will be populated after successful creation.
	Create(ctx context.Context, document *models.Document) error

	// GetByID retrieves a document by its unique identifier.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - id: The unique identifier of the document
	//
	// Returns:
	//   - The document if found
	//   - NotFoundError if the document doesn't exist
	//   - Other errors for database issues
	GetByID(ctx context.Context, id int64) (*models.Document, error)

	// GetByUserID retrieves all documents for a user with pagination.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - userID: The unique identifier of the user
	//   - page: The page number (starting from 1)
	//   - pageSize: The number of documents per page
	//
	// Returns:
	//   - A slice of documents owned by the user for the requested page
	//   - The total count of documents owned by the user
	//   - An error if retrieval fails
	GetByUserID(ctx context.Context, userID int64, page, pageSize int) ([]*models.Document, int, error)

	// Update updates a document in the database.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - document: The document to update
	//
	// Returns:
	//   - NotFoundError if the document doesn't exist
	//   - Other errors for database issues
	//
	// This method automatically updates the LastModified timestamp.
	Update(ctx context.Context, document *models.Document) error

	// Delete removes a document and all its detected entities.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - id: The unique identifier of the document to delete
	//
	// Returns:
	//   - NotFoundError if the document doesn't exist
	//   - Other errors for database issues
	//
	// This operation uses a transaction to ensure the document and all its entities
	// are deleted atomically.
	Delete(ctx context.Context, id int64) error

	// DeleteByUserID removes all documents for a user.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - userID: The unique identifier of the user
	//
	// Returns:
	//   - An error if deletion fails
	//   - nil if deletion succeeds
	//
	// This operation uses a transaction to ensure all documents and their entities
	// are deleted atomically.
	DeleteByUserID(ctx context.Context, userID int64) error

	// GetDetectedEntities retrieves all detected entities for a document.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - documentID: The unique identifier of the document
	//
	// Returns:
	//   - A slice of detected entities with their associated detection methods
	//   - An empty slice if the document has no detected entities
	//   - An error if retrieval fails
	GetDetectedEntities(ctx context.Context, documentID int64) ([]*models.DetectedEntityWithMethod, error)

	// AddDetectedEntity adds a new detected entity to a document.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - entity: The detected entity to add
	//
	// Returns:
	//   - An error if addition fails
	//   - nil on successful addition
	//
	// The entity ID will be populated after successful addition.
	AddDetectedEntity(ctx context.Context, entity *models.DetectedEntity) error

	// DeleteDetectedEntity removes a detected entity.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - entityID: The unique identifier of the entity to delete
	//
	// Returns:
	//   - NotFoundError if the entity doesn't exist
	//   - Other errors for database issues
	DeleteDetectedEntity(ctx context.Context, entityID int64) error

	// GetDocumentSummary retrieves a summary of a document including entity count.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation control
	//   - documentID: The unique identifier of the document
	//
	// Returns:
	//   - A document summary with metadata and entity count
	//   - NotFoundError if the document doesn't exist
	//   - Other errors for database issues
	GetDocumentSummary(ctx context.Context, documentID int64) (*models.DocumentSummary, error)
}

// PostgresDocumentRepository is a PostgreSQL implementation of DocumentRepository.
// It implements all required methods using PostgreSQL-specific features
// and error handling.
type PostgresDocumentRepository struct {
	db            *database.Pool
	encryptionKey []byte
}

// NewDocumentRepository creates a new DocumentRepository implementation for PostgreSQL.
// Accepts an encryption key for document name encryption.
func NewDocumentRepository(db *database.Pool, encryptionKey []byte) DocumentRepository {
	return &PostgresDocumentRepository{
		db:            db,
		encryptionKey: encryptionKey,
	}
}

// Create adds a new document to the database.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - document: The document to store
//
// Returns:
//   - An error if creation fails
//   - nil on successful creation
//
// The document ID will be populated after successful creation.
func (r *PostgresDocumentRepository) Create(ctx context.Context, document *models.Document) error {
	// Start query timer
	startTime := time.Now()

	// Encrypt the document name before saving
	encryptedName, err := utils.EncryptKey(document.HashedDocumentName, r.encryptionKey)
	if err != nil {
		return fmt.Errorf("failed to encrypt document name: %w", err)
	}
	// Define the query with RETURNING for PostgreSQL
	query := `
        INSERT INTO ` + constants.TableDocuments + ` (` + constants.ColumnUserID + `, hashed_document_name, upload_timestamp, last_modified, redaction_schema)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING ` + constants.ColumnDocumentID + `
    `

	// Execute the query
	err = r.db.QueryRowContext(
		ctx,
		query,
		document.UserID,
		encryptedName,
		document.UploadTimestamp,
		document.LastModified,
		document.RedactionSchema,
	).Scan(&document.ID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{document.UserID, encryptedName, document.UploadTimestamp, document.LastModified, document.RedactionSchema},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to create document: %w", err)
	}

	log.Info().
		Int64(constants.ColumnDocumentID, document.ID).
		Int64(constants.ColumnUserID, document.UserID).
		Msg("Document created")

	return nil
}

// GetByID retrieves a document by ID.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - id: The unique identifier of the document
//
// Returns:
//   - The document if found
//   - NotFoundError if the document doesn't exist
//   - Other errors for database issues
func (r *PostgresDocumentRepository) GetByID(ctx context.Context, id int64) (*models.Document, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT ` + constants.ColumnDocumentID + `, ` + constants.ColumnUserID + `, hashed_document_name, upload_timestamp, last_modified, redaction_schema
        FROM ` + constants.TableDocuments + `
        WHERE ` + constants.ColumnDocumentID + ` = $1
    `

	// Execute the query
	document := &models.Document{}
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&document.ID,
		&document.UserID,
		&document.HashedDocumentName,
		&document.UploadTimestamp,
		&document.LastModified,
		&document.RedactionSchema,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{id},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewNotFoundError("Document", id)
		}
		return nil, fmt.Errorf("failed to get document by ID: %w", err)
	}

	// Decrypt the document name before returning
	decryptedName, err := utils.DecryptKey(document.HashedDocumentName, r.encryptionKey)
	if err != nil {
		return nil, fmt.Errorf("failed to decrypt document name: %w", err)
	}

	document.HashedDocumentName = decryptedName
	return document, nil
}

// GetByUserID retrieves all documents for a user with pagination.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - userID: The unique identifier of the user
//   - page: The page number (starting from 1)
//   - pageSize: The number of documents per page
//
// Returns:
//   - A slice of documents owned by the user for the requested page
//   - The total count of documents owned by the user
//   - An error if retrieval fails
func (r *PostgresDocumentRepository) GetByUserID(ctx context.Context, userID int64, page, pageSize int) ([]*models.Document, int, error) {
	// Start query timer
	startTime := time.Now()

	// Calculate offset
	offset := (page - 1) * pageSize

	// Get total count
	countQuery := `SELECT COUNT(*) FROM ` + constants.TableDocuments + ` WHERE ` + constants.ColumnUserID + ` = $1`
	var totalCount int
	if err := r.db.QueryRowContext(ctx, countQuery, userID).Scan(&totalCount); err != nil {
		return nil, 0, fmt.Errorf("failed to count documents: %w", err)
	}

	// Define the query
	query := `
        SELECT ` + constants.ColumnDocumentID + `, ` + constants.ColumnUserID + `, hashed_document_name, upload_timestamp, last_modified, redaction_schema
        FROM ` + constants.TableDocuments + `
        WHERE ` + constants.ColumnUserID + ` = $1
        ORDER BY upload_timestamp DESC
        LIMIT $2 OFFSET $3
    `

	// Execute the query
	rows, err := r.db.QueryContext(ctx, query, userID, pageSize, offset)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{userID, pageSize, offset},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return nil, 0, fmt.Errorf("failed to get documents by user ID: %w", err)
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	// Parse the results
	var documents []*models.Document
	for rows.Next() {
		document := &models.Document{}
		if err := rows.Scan(
			&document.ID,
			&document.UserID,
			&document.HashedDocumentName,
			&document.UploadTimestamp,
			&document.LastModified,
			&document.RedactionSchema,
		); err != nil {
			return nil, 0, fmt.Errorf("failed to scan document row: %w", err)
		}

		// Decrypt the document name before returning
		decryptedName, err := utils.DecryptKey(document.HashedDocumentName, r.encryptionKey)
		if err != nil {
			return nil, 0, fmt.Errorf("failed to decrypt document name: %w", err)
		}
		document.HashedDocumentName = decryptedName

		documents = append(documents, document)
	}

	if err := rows.Err(); err != nil {
		return nil, 0, fmt.Errorf("error iterating document rows: %w", err)
	}

	return documents, totalCount, nil
}

// Update updates a document in the database.
// This method automatically updates the LastModified timestamp.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - document: The document to update
//
// Returns:
//   - NotFoundError if the document doesn't exist
//   - Other errors for database issues
func (r *PostgresDocumentRepository) Update(ctx context.Context, document *models.Document) error {
	// Start query timer
	startTime := time.Now()

	// Update the last modified timestamp
	document.LastModified = time.Now()

	// Define the query
	query := `
        UPDATE ` + constants.TableDocuments + `
        SET last_modified = $1
        WHERE ` + constants.ColumnDocumentID + ` = $2
    `

	// Execute the query
	result, err := r.db.ExecContext(
		ctx,
		query,
		document.LastModified,
		document.ID,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{document.LastModified, document.ID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to update document: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("Document", document.ID)
	}

	log.Info().
		Int64(constants.ColumnDocumentID, document.ID).
		Msg("Document updated")

	return nil
}

// Delete removes a document and all its detected entities.
// This operation uses a transaction to ensure the document and all its entities
// are deleted atomically.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - id: The unique identifier of the document to delete
//
// Returns:
//   - NotFoundError if the document doesn't exist
//   - Other errors for database issues
func (r *PostgresDocumentRepository) Delete(ctx context.Context, id int64) error {
	// Start query timer
	startTime := time.Now()

	// Execute the delete within a transaction to cascade properly
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// First delete all detected entities
		entitiesQuery := "DELETE FROM " + constants.TableDetectedEntities + " WHERE " + constants.ColumnDocumentID + " = $1"
		_, err := tx.ExecContext(ctx, entitiesQuery, id)
		if err != nil {
			return fmt.Errorf("failed to delete detected entities: %w", err)
		}

		// Then delete the document
		documentQuery := "DELETE FROM " + constants.TableDocuments + " WHERE " + constants.ColumnDocumentID + " = $1"
		result, err := tx.ExecContext(ctx, documentQuery, id)

		// Log the query execution
		utils.LogDBQuery(
			documentQuery,
			[]interface{}{id},
			time.Since(startTime),
			err,
		)

		if err != nil {
			return fmt.Errorf("failed to delete document: %w", err)
		}

		// Check if any rows were affected
		rowsAffected, err := result.RowsAffected()
		if err != nil {
			return fmt.Errorf("failed to get rows affected: %w", err)
		}

		if rowsAffected == 0 {
			return utils.NewNotFoundError("Document", id)
		}

		log.Info().
			Int64(constants.ColumnDocumentID, id).
			Msg("Document deleted")

		return nil
	})
}

// DeleteByUserID removes all documents for a user.
// This operation first identifies all documents for the user, then
// deletes all detected entities for those documents, and finally
// deletes the documents themselves. All operations are performed
// within a transaction to ensure consistency.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - userID: The unique identifier of the user
//
// Returns:
//   - An error if deletion fails
//   - nil if deletion succeeds
func (r *PostgresDocumentRepository) DeleteByUserID(ctx context.Context, userID int64) error {
	// Start query timer
	startTime := time.Now()

	// Execute the delete within a transaction to cascade properly
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// First get all document IDs
		documentIDsQuery := "SELECT " + constants.ColumnDocumentID + " FROM " + constants.TableDocuments + " WHERE " + constants.ColumnUserID + " = $1"
		rows, err := tx.QueryContext(ctx, documentIDsQuery, userID)
		if err != nil {
			return fmt.Errorf("failed to get document IDs: %w", err)
		}
		defer rows.Close()

		var documentIDs []int64
		for rows.Next() {
			var documentID int64
			if err := rows.Scan(&documentID); err != nil {
				return fmt.Errorf("failed to scan document ID: %w", err)
			}
			documentIDs = append(documentIDs, documentID)
		}

		if err := rows.Err(); err != nil {
			return fmt.Errorf("error iterating document ID rows: %w", err)
		}

		// Delete all detected entities for these documents
		if len(documentIDs) > 0 {
			for _, documentID := range documentIDs {
				entitiesQuery := "DELETE FROM " + constants.TableDetectedEntities + " WHERE " + constants.ColumnDocumentID + " = $1"
				_, err := tx.ExecContext(ctx, entitiesQuery, documentID)
				if err != nil {
					return fmt.Errorf("failed to delete detected entities: %w", err)
				}
			}
		}

		// Then delete all documents
		documentsQuery := "DELETE FROM " + constants.TableDocuments + " WHERE " + constants.ColumnUserID + " = $1"
		result, err := tx.ExecContext(ctx, documentsQuery, userID)

		// Log the query execution
		utils.LogDBQuery(
			documentsQuery,
			[]interface{}{userID},
			time.Since(startTime),
			err,
		)

		if err != nil {
			return fmt.Errorf("failed to delete documents by user ID: %w", err)
		}

		// Log the deletion
		rowsAffected, _ := result.RowsAffected()
		log.Info().
			Int64(constants.ColumnUserID, userID).
			Int64("count", rowsAffected).
			Msg("Documents deleted for user")

		return nil
	})
}

// GetDetectedEntities retrieves all detected entities for a document.
// It also decrypts the redaction schemas before returning.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - documentID: The unique identifier of the document
//
// Returns:
//   - A slice of detected entities with their associated detection methods
//   - An empty slice if the document has no detected entities
//   - An error if retrieval fails
func (r *PostgresDocumentRepository) GetDetectedEntities(ctx context.Context, documentID int64) ([]*models.DetectedEntityWithMethod, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT de.` + constants.ColumnEntityID + `, de.` + constants.ColumnDocumentID + `, de.` + constants.ColumnMethodID + `, de.` + constants.ColumnEntityName + `, de.redaction_schema, de.detected_timestamp,
               dm.` + constants.ColumnMethodName + `, dm.` + constants.ColumnHighlightColor + `
        FROM ` + constants.TableDetectedEntities + ` de
        JOIN ` + constants.TableDetectionMethods + ` dm ON de.` + constants.ColumnMethodID + ` = dm.` + constants.ColumnMethodID + `
        WHERE de.` + constants.ColumnDocumentID + ` = $1
        ORDER BY de.detected_timestamp DESC
    `

	// Execute the query
	rows, err := r.db.QueryContext(ctx, query, documentID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{documentID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get detected entities: %w", err)
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	// Parse the results
	var entities []*models.DetectedEntityWithMethod
	for rows.Next() {
		entity := &models.DetectedEntityWithMethod{
			DetectedEntity: models.DetectedEntity{},
		}
		if err := rows.Scan(
			&entity.ID,
			&entity.DocumentID,
			&entity.MethodID,
			&entity.EntityName,
			&entity.RedactionSchema,
			&entity.DetectedTimestamp,
			&entity.MethodName,
			&entity.HighlightColor,
		); err != nil {
			return nil, fmt.Errorf("failed to scan detected entity row: %w", err)
		}

		// Decrypt the redaction schema
		if err := entity.DecryptRedactionSchema(r.encryptionKey); err != nil {
			return nil, fmt.Errorf("failed to decrypt redaction schema for entity %d: %w", entity.ID, err)
		}

		entities = append(entities, entity)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating detected entity rows: %w", err)
	}

	return entities, nil
}

// AddDetectedEntity adds a new detected entity to the database.
// This creates a record of sensitive information found in a document.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - entity: The detected entity to add
//
// Returns:
//   - An error if addition fails
//   - nil on successful addition
//
// The entity ID will be populated after successful addition.
func (r *PostgresDocumentRepository) AddDetectedEntity(ctx context.Context, entity *models.DetectedEntity) error {
	// Start query timer
	startTime := time.Now()

	// Encrypt the redaction schema before storing
	if err := entity.EncryptRedactionSchema(r.encryptionKey); err != nil {
		return fmt.Errorf("failed to encrypt redaction schema: %w", err)
	}

	// Define the query with RETURNING for PostgreSQL
	query := `
        INSERT INTO ` + constants.TableDetectedEntities + ` (` + constants.ColumnDocumentID + `, ` + constants.ColumnMethodID + `, ` + constants.ColumnEntityName + `, redaction_schema, detected_timestamp)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING ` + constants.ColumnEntityID + `
    `

	// Execute the query
	err := r.db.QueryRowContext(
		ctx,
		query,
		entity.DocumentID,
		entity.MethodID,
		entity.EntityName,
		entity.RedactionSchema,
		entity.DetectedTimestamp,
	).Scan(&entity.ID)

	// Log the query execution (without sensitive data)
	utils.LogDBQuery(
		query,
		[]interface{}{entity.DocumentID, entity.MethodID, entity.EntityName, "redactionSchema", entity.DetectedTimestamp},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to create detected entity: %w", err)
	}

	log.Info().
		Int64(constants.ColumnEntityID, entity.ID).
		Int64(constants.ColumnDocumentID, entity.DocumentID).
		Int64(constants.ColumnMethodID, entity.MethodID).
		Str(constants.ColumnEntityName, entity.EntityName).
		Msg("Detected entity created")

	return nil
}

// DeleteDetectedEntity removes a detected entity from the database.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - entityID: The unique identifier of the entity to delete
//
// Returns:
//   - NotFoundError if the entity doesn't exist
//   - Other errors for database issues
func (r *PostgresDocumentRepository) DeleteDetectedEntity(ctx context.Context, entityID int64) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM ` + constants.TableDetectedEntities + ` WHERE ` + constants.ColumnEntityID + ` = $1`

	// Execute the query
	result, err := r.db.ExecContext(ctx, query, entityID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{entityID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to delete detected entity: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("DetectedEntity", entityID)
	}

	log.Info().
		Int64(constants.ColumnEntityID, entityID).
		Msg("Detected entity deleted")

	return nil
}

// GetDocumentSummary retrieves a summary of a document including the entity count.
// This method performs a join between the documents table and detected entities table
// to count entities in a single query.
//
// Parameters:
//   - ctx: Context for transaction and cancellation control
//   - documentID: The unique identifier of the document
//
// Returns:
//   - A document summary with metadata and entity count
//   - NotFoundError if the document doesn't exist
//   - Other errors for database issues
func (r *PostgresDocumentRepository) GetDocumentSummary(ctx context.Context, documentID int64) (*models.DocumentSummary, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT d.` + constants.ColumnDocumentID + `, d.hashed_document_name, d.upload_timestamp, d.last_modified,
               COUNT(de.` + constants.ColumnEntityID + `) AS entity_count
        FROM ` + constants.TableDocuments + ` d
        LEFT JOIN ` + constants.TableDetectedEntities + ` de ON d.` + constants.ColumnDocumentID + ` = de.` + constants.ColumnDocumentID + `
        WHERE d.` + constants.ColumnDocumentID + ` = $1
        GROUP BY d.` + constants.ColumnDocumentID + `
    `

	// Execute the query
	summary := &models.DocumentSummary{}
	err := r.db.QueryRowContext(ctx, query, documentID).Scan(
		&summary.ID,
		&summary.HashedName,
		&summary.UploadTimestamp,
		&summary.LastModified,
		&summary.EntityCount,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{documentID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewNotFoundError("Document", documentID)
		}
		return nil, fmt.Errorf("failed to get document summary: %w", err)
	}

	// Decrypt the document name before returning
	decryptedName, err := utils.DecryptKey(summary.HashedName, r.encryptionKey)
	if err != nil {
		return nil, fmt.Errorf("failed to decrypt document name: %w", err)
	}
	summary.HashedName = decryptedName

	return summary, nil
}
