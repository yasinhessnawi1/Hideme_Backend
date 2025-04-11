package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// DocumentRepository defines methods for interacting with documents
type DocumentRepository interface {
	Create(ctx context.Context, document *models.Document) error
	GetByID(ctx context.Context, id int64) (*models.Document, error)
	GetByUserID(ctx context.Context, userID int64, page, pageSize int) ([]*models.Document, int, error)
	Update(ctx context.Context, document *models.Document) error
	Delete(ctx context.Context, id int64) error
	DeleteByUserID(ctx context.Context, userID int64) error
	GetDetectedEntities(ctx context.Context, documentID int64) ([]*models.DetectedEntityWithMethod, error)
	AddDetectedEntity(ctx context.Context, entity *models.DetectedEntity) error
	DeleteDetectedEntity(ctx context.Context, entityID int64) error
	GetDocumentSummary(ctx context.Context, documentID int64) (*models.DocumentSummary, error)
}

// PostgresDocumentRepository is a PostgreSQL implementation of DocumentRepository
type PostgresDocumentRepository struct {
	db *database.Pool
}

// NewDocumentRepository creates a new DocumentRepository
func NewDocumentRepository(db *database.Pool) DocumentRepository {
	return &PostgresDocumentRepository{
		db: db,
	}
}

// Create adds a new document to the database
func (r *PostgresDocumentRepository) Create(ctx context.Context, document *models.Document) error {
	// Start query timer
	startTime := time.Now()

	// Define the query with RETURNING for PostgreSQL
	query := `
        INSERT INTO documents (user_id, hashed_document_name, upload_timestamp, last_modified)
        VALUES ($1, $2, $3, $4)
        RETURNING document_id
    `

	// Execute the query
	err := r.db.QueryRowContext(
		ctx,
		query,
		document.UserID,
		document.HashedDocumentName,
		document.UploadTimestamp,
		document.LastModified,
	).Scan(&document.ID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{document.UserID, document.HashedDocumentName, document.UploadTimestamp, document.LastModified},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to create document: %w", err)
	}

	log.Info().
		Int64("document_id", document.ID).
		Int64("user_id", document.UserID).
		Msg("Document created")

	return nil
}

// GetByID retrieves a document by ID
func (r *PostgresDocumentRepository) GetByID(ctx context.Context, id int64) (*models.Document, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified
        FROM documents
        WHERE document_id = $1
    `

	// Execute the query
	document := &models.Document{}
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&document.ID,
		&document.UserID,
		&document.HashedDocumentName,
		&document.UploadTimestamp,
		&document.LastModified,
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

	return document, nil
}

// GetByUserID retrieves all documents for a user with pagination
func (r *PostgresDocumentRepository) GetByUserID(ctx context.Context, userID int64, page, pageSize int) ([]*models.Document, int, error) {
	// Start query timer
	startTime := time.Now()

	// Calculate offset
	offset := (page - 1) * pageSize

	// Get total count
	countQuery := `SELECT COUNT(*) FROM documents WHERE user_id = $1`
	var totalCount int
	if err := r.db.QueryRowContext(ctx, countQuery, userID).Scan(&totalCount); err != nil {
		return nil, 0, fmt.Errorf("failed to count documents: %w", err)
	}

	// Define the query
	query := `
        SELECT document_id, user_id, hashed_document_name, upload_timestamp, last_modified
        FROM documents
        WHERE user_id = $1
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
		); err != nil {
			return nil, 0, fmt.Errorf("failed to scan document row: %w", err)
		}
		documents = append(documents, document)
	}

	if err := rows.Err(); err != nil {
		return nil, 0, fmt.Errorf("error iterating document rows: %w", err)
	}

	return documents, totalCount, nil
}

// Update updates a document in the database
func (r *PostgresDocumentRepository) Update(ctx context.Context, document *models.Document) error {
	// Start query timer
	startTime := time.Now()

	// Update the last modified timestamp
	document.LastModified = time.Now()

	// Define the query
	query := `
        UPDATE documents
        SET last_modified = $1
        WHERE document_id = $2
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
		Int64("document_id", document.ID).
		Msg("Document updated")

	return nil
}

// Delete removes a document and all its detected entities
func (r *PostgresDocumentRepository) Delete(ctx context.Context, id int64) error {
	// Start query timer
	startTime := time.Now()

	// Execute the delete within a transaction to cascade properly
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// First delete all detected entities
		entitiesQuery := "DELETE FROM detected_entities WHERE document_id = $1"
		_, err := tx.ExecContext(ctx, entitiesQuery, id)
		if err != nil {
			return fmt.Errorf("failed to delete detected entities: %w", err)
		}

		// Then delete the document
		documentQuery := "DELETE FROM documents WHERE document_id = $1"
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
			Int64("document_id", id).
			Msg("Document deleted")

		return nil
	})
}

// DeleteByUserID removes all documents for a user
func (r *PostgresDocumentRepository) DeleteByUserID(ctx context.Context, userID int64) error {
	// Start query timer
	startTime := time.Now()

	// Execute the delete within a transaction to cascade properly
	return r.db.Transaction(ctx, func(tx *sql.Tx) error {
		// First get all document IDs
		documentIDsQuery := "SELECT document_id FROM documents WHERE user_id = $1"
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
				entitiesQuery := "DELETE FROM detected_entities WHERE document_id = $1"
				_, err := tx.ExecContext(ctx, entitiesQuery, documentID)
				if err != nil {
					return fmt.Errorf("failed to delete detected entities: %w", err)
				}
			}
		}

		// Then delete all documents
		documentsQuery := "DELETE FROM documents WHERE user_id = $1"
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
			Int64("user_id", userID).
			Int64("count", rowsAffected).
			Msg("Documents deleted for user")

		return nil
	})
}

// GetDetectedEntities retrieves all detected entities for a document with method information
func (r *PostgresDocumentRepository) GetDetectedEntities(ctx context.Context, documentID int64) ([]*models.DetectedEntityWithMethod, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT de.entity_id, de.document_id, de.method_id, de.entity_name, de.redaction_schema, de.detected_timestamp,
               dm.method_name, dm.highlight_color
        FROM detected_entities de
        JOIN detection_methods dm ON de.method_id = dm.method_id
        WHERE de.document_id = $1
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
		entities = append(entities, entity)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating detected entity rows: %w", err)
	}

	return entities, nil
}

// AddDetectedEntity adds a new detected entity to the database
func (r *PostgresDocumentRepository) AddDetectedEntity(ctx context.Context, entity *models.DetectedEntity) error {
	// Start query timer
	startTime := time.Now()

	// Define the query with RETURNING for PostgreSQL
	query := `
        INSERT INTO detected_entities (document_id, method_id, entity_name, redaction_schema, detected_timestamp)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING entity_id
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
		Int64("entity_id", entity.ID).
		Int64("document_id", entity.DocumentID).
		Int64("method_id", entity.MethodID).
		Str("entity_name", entity.EntityName).
		Msg("Detected entity created")

	return nil
}

// DeleteDetectedEntity removes a detected entity from the database
func (r *PostgresDocumentRepository) DeleteDetectedEntity(ctx context.Context, entityID int64) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM detected_entities WHERE entity_id = $1`

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
		Int64("entity_id", entityID).
		Msg("Detected entity deleted")

	return nil
}

// GetDocumentSummary retrieves a summary of a document including the entity count
func (r *PostgresDocumentRepository) GetDocumentSummary(ctx context.Context, documentID int64) (*models.DocumentSummary, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
        SELECT d.document_id, d.hashed_document_name, d.upload_timestamp, d.last_modified,
               COUNT(de.entity_id) AS entity_count
        FROM documents d
        LEFT JOIN detected_entities de ON d.document_id = de.document_id
        WHERE d.document_id = $1
        GROUP BY d.document_id
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

	return summary, nil
}
