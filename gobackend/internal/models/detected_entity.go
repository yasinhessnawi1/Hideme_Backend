// Package models provides data structures and operations for the HideMe application.
// It contains models for document processing, entity detection, and redaction operations
// that are central to the application's privacy protection features.
//
// The models in this package adhere to data minimization principles and support
// secure handling of sensitive information in compliance with privacy regulations.
package models

import (
	"database/sql/driver"
	"encoding/json"
	"errors"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// DetectedEntity represents sensitive information identified within a document.
// It stores both the entity itself and structured information about its position and redaction.
// Each entity is linked to a document and detection method, allowing for tracking of
// how sensitive information was discovered.
type DetectedEntity struct {
	// ID is the unique identifier for this detected entity.
	ID int64 `json:"id" db:"entity_id"`

	// DocumentID references the document in which this entity was detected.
	DocumentID int64 `json:"document_id" db:"document_id"`

	// MethodID references the detection method used to identify this entity.
	MethodID int64 `json:"method_id" db:"method_id"`

	// EntityName contains the actual sensitive information detected.
	// Note: This field contains sensitive data and should be handled according to privacy policies.
	EntityName string `json:"entity_name" db:"entity_name"`

	// RedactionSchema contains positional and styling information for redaction.
	RedactionSchema RedactionSchema `json:"redaction_schema" db:"redaction_schema"`

	// DetectedTimestamp records when this entity was detected.
	DetectedTimestamp time.Time `json:"detected_timestamp" db:"detected_timestamp"`
}

// TableName returns the database table name for the DetectedEntity model.
// This method is used by ORM frameworks to determine where to persist this entity.
func (de *DetectedEntity) TableName() string {
	return constants.TableDetectedEntities
}

// NewDetectedEntity creates a new DetectedEntity instance with the given parameters.
// It automatically sets the detection timestamp to the current time.
//
// Parameters:
//   - documentID: The ID of the document where the entity was found
//   - methodID: The ID of the detection method used to find the entity
//   - entityName: The sensitive information that was detected
//   - schema: Positional and styling information for redaction
//
// Returns:
//   - A new DetectedEntity pointer with all fields populated
func NewDetectedEntity(documentID, methodID int64, entityName string, schema RedactionSchema) *DetectedEntity {
	return &DetectedEntity{
		DocumentID:        documentID,
		MethodID:          methodID,
		EntityName:        entityName,
		RedactionSchema:   schema,
		DetectedTimestamp: time.Now(),
	}
}

// RedactionSchema represents structured information about entity position and redaction details.
// It is stored as JSON in the database to provide flexibility for different document types.
// This structure enables precise redaction across various document formats.
type RedactionSchema struct {
	// Page number where the entity appears (for multi-page documents)
	Page int `json:"page"`

	// Position coordinates
	StartX float64 `json:"start_x"`
	StartY float64 `json:"start_y"`
	EndX   float64 `json:"end_x"`
	EndY   float64 `json:"end_y"`

	// Additional context for redaction
	SurroundingContext string `json:"surrounding_context,omitempty"`

	// Redaction parameters
	// RedactionMethod defines how the entity should be redacted (e.g., "blackout", "replace", "mask")
	RedactionMethod string `json:"redaction_method"`

	// ReplacementValue is the text to use when RedactionMethod is "replace"
	ReplacementValue string `json:"replacement_value,omitempty"`
}

// Value implements the driver.Valuer interface for RedactionSchema.
// This allows the custom type to be stored in the database as JSON.
//
// Returns:
//   - The JSON representation of RedactionSchema as a driver.Value
//   - An error if JSON marshaling fails
func (rs RedactionSchema) Value() (driver.Value, error) {
	return json.Marshal(rs)
}

// Scan implements the sql.Scanner interface for RedactionSchema.
// This allows the JSON from the database to be converted back into the custom type.
//
// Parameters:
//   - value: The database value to scan (expected to be []byte)
//
// Returns:
//   - An error if type assertion or JSON unmarshaling fails
func (rs *RedactionSchema) Scan(value interface{}) error {
	bytes, ok := value.([]byte)
	if !ok {
		return errors.New("type assertion to []byte failed")
	}

	return json.Unmarshal(bytes, &rs)
}

// DetectedEntityWithMethod represents a detected entity with its associated detection method.
// This is a convenience struct for API responses that need method information.
// It extends DetectedEntity with method-specific fields to avoid multiple database lookups.
type DetectedEntityWithMethod struct {
	DetectedEntity

	// MethodName is the name of the detection method used
	MethodName string `json:"method_name"`

	// HighlightColor defines the visual representation of this entity in the UI
	HighlightColor string `json:"highlight_color"`
}
