package models_test

import (
	"database/sql/driver"
	"encoding/json"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestDetectedEntity_TableName(t *testing.T) {
	// Create a test detected entity
	entity := &models.DetectedEntity{
		ID:         1,
		DocumentID: 100,
		MethodID:   5,
		EntityName: "Test Entity",
	}

	// Verify the table name
	tableName := entity.TableName()
	assert.Equal(t, "detected_entities", tableName, "TableName should return the correct database table name")
}

func TestNewDetectedEntity(t *testing.T) {
	// Test parameters
	documentID := int64(123)
	methodID := int64(5)
	entityName := "Test Entity"
	schema := models.RedactionSchema{
		Page:               1,
		StartX:             10.5,
		StartY:             20.5,
		EndX:               30.5,
		EndY:               40.5,
		SurroundingContext: "Sample context",
		RedactionMethod:    "blackout",
		ReplacementValue:   "REDACTED",
	}

	// Create a new detected entity
	now := time.Now()
	entity := models.NewDetectedEntity(documentID, methodID, entityName, schema)

	// Verify the entity was created correctly
	assert.NotNil(t, entity, "NewDetectedEntity should return a non-nil DetectedEntity")
	assert.Equal(t, documentID, entity.DocumentID, "DetectedEntity should have the provided document ID")
	assert.Equal(t, methodID, entity.MethodID, "DetectedEntity should have the provided method ID")
	assert.Equal(t, entityName, entity.EntityName, "DetectedEntity should have the provided entity name")
	assert.Equal(t, schema, entity.RedactionSchema, "DetectedEntity should have the provided redaction schema")
	assert.WithinDuration(t, now, entity.DetectedTimestamp, time.Second, "DetectedTimestamp should be set to current time")
	assert.Equal(t, int64(0), entity.ID, "A new DetectedEntity should have zero ID until saved to database")
}

func TestRedactionSchema_Value(t *testing.T) {
	// Create a test redaction schema
	schema := models.RedactionSchema{
		Page:               2,
		StartX:             15.5,
		StartY:             25.5,
		EndX:               35.5,
		EndY:               45.5,
		SurroundingContext: "Test context",
		RedactionMethod:    "replace",
		ReplacementValue:   "HIDDEN",
	}

	// Get the value for database storage
	value, err := schema.Value()

	// Verify the value
	assert.NoError(t, err, "Value() should not return an error")
	assert.NotNil(t, value, "Value() should return a non-nil value")

	// Verify the value is the JSON representation of the schema
	expectedJSON, _ := json.Marshal(schema)
	assert.Equal(t, driver.Value(expectedJSON), value, "Value() should return the JSON representation of the schema")
}

func TestRedactionSchema_Scan(t *testing.T) {
	// Create a test redaction schema
	originalSchema := models.RedactionSchema{
		Page:               3,
		StartX:             12.5,
		StartY:             22.5,
		EndX:               32.5,
		EndY:               42.5,
		SurroundingContext: "Another context",
		RedactionMethod:    "mask",
		ReplacementValue:   "***",
	}

	// Convert to JSON for scanning
	jsonBytes, _ := json.Marshal(originalSchema)

	// Create a new schema to scan into
	var scannedSchema models.RedactionSchema

	// Scan the JSON into the schema
	err := scannedSchema.Scan(jsonBytes)

	// Verify scanning worked correctly
	assert.NoError(t, err, "Scan() should not return an error")
	assert.Equal(t, originalSchema, scannedSchema, "Scan() should correctly reconstruct the schema from JSON")

	// Test scanning with invalid value type
	err = scannedSchema.Scan(123) // Not a []byte
	assert.Error(t, err, "Scan() should return an error when given a non-[]byte value")
}

func TestDetectedEntityWithMethod(t *testing.T) {
	// Create a test detected entity with method
	entityWithMethod := &models.DetectedEntityWithMethod{
		DetectedEntity: models.DetectedEntity{
			ID:         1,
			DocumentID: 100,
			MethodID:   5,
			EntityName: "Test Entity",
		},
		MethodName:     "Test Method",
		HighlightColor: "#FF5733",
	}

	// Verify the fields
	assert.Equal(t, int64(1), entityWithMethod.ID)
	assert.Equal(t, int64(100), entityWithMethod.DocumentID)
	assert.Equal(t, int64(5), entityWithMethod.MethodID)
	assert.Equal(t, "Test Entity", entityWithMethod.EntityName)
	assert.Equal(t, "Test Method", entityWithMethod.MethodName)
	assert.Equal(t, "#FF5733", entityWithMethod.HighlightColor)
}
