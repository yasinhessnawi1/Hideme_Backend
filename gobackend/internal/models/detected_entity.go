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
type DetectedEntity struct {
	ID                int64           `json:"id" db:"entity_id"`
	DocumentID        int64           `json:"document_id" db:"document_id"`
	MethodID          int64           `json:"method_id" db:"method_id"`
	EntityName        string          `json:"entity_name" db:"entity_name"`
	RedactionSchema   RedactionSchema `json:"redaction_schema" db:"redaction_schema"`
	DetectedTimestamp time.Time       `json:"detected_timestamp" db:"detected_timestamp"`
}

// TableName returns the database table name for the DetectedEntity model.
func (de *DetectedEntity) TableName() string {
	return constants.TableDetectedEntities
}

// NewDetectedEntity creates a new DetectedEntity instance with the given parameters.
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
	RedactionMethod  string `json:"redaction_method"` // e.g., "blackout", "replace", "mask"
	ReplacementValue string `json:"replacement_value,omitempty"`
}

// Value implements the driver.Valuer interface for RedactionSchema.
// This allows the custom type to be stored in the database as JSON.
func (rs RedactionSchema) Value() (driver.Value, error) {
	return json.Marshal(rs)
}

// Scan implements the sql.Scanner interface for RedactionSchema.
// This allows the JSON from the database to be converted back into the custom type.
func (rs *RedactionSchema) Scan(value interface{}) error {
	bytes, ok := value.([]byte)
	if !ok {
		return errors.New("type assertion to []byte failed")
	}

	return json.Unmarshal(bytes, &rs)
}

// DetectedEntityWithMethod represents a detected entity with its associated detection method.
// This is a convenience struct for API responses that need method information.
type DetectedEntityWithMethod struct {
	DetectedEntity
	MethodName     string `json:"method_name"`
	HighlightColor string `json:"highlight_color"`
}
