package models_test

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestModelEntity_TableName(t *testing.T) {
	// Create a test model entity
	entity := &models.ModelEntity{
		ID:         1,
		SettingID:  100,
		MethodID:   5,
		EntityText: "Test Entity",
	}

	// Verify the table name
	tableName := entity.TableName()
	assert.Equal(t, "model_entities", tableName, "TableName should return the correct database table name")
}

func TestNewModelEntity(t *testing.T) {
	// Test parameters
	settingID := int64(100)
	methodID := int64(5)
	entityText := "Credit Card Number"

	// Create a new model entity
	entity := models.NewModelEntity(settingID, methodID, entityText)

	// Verify the entity was created correctly
	assert.NotNil(t, entity, "NewModelEntity should return a non-nil ModelEntity")
	assert.Equal(t, settingID, entity.SettingID, "ModelEntity should have the provided setting ID")
	assert.Equal(t, methodID, entity.MethodID, "ModelEntity should have the provided method ID")
	assert.Equal(t, entityText, entity.EntityText, "ModelEntity should have the provided entity text")
	assert.Equal(t, int64(0), entity.ID, "A new ModelEntity should have zero ID until saved to database")
}

func TestModelEntityWithMethod(t *testing.T) {
	// Create a test model entity with method
	entityWithMethod := &models.ModelEntityWithMethod{
		ModelEntity: models.ModelEntity{
			ID:         1,
			SettingID:  100,
			MethodID:   5,
			EntityText: "Test Entity",
		},
		MethodName: "Test Method",
	}

	// Verify the fields
	assert.Equal(t, int64(1), entityWithMethod.ID)
	assert.Equal(t, int64(100), entityWithMethod.SettingID)
	assert.Equal(t, int64(5), entityWithMethod.MethodID)
	assert.Equal(t, "Test Entity", entityWithMethod.EntityText)
	assert.Equal(t, "Test Method", entityWithMethod.MethodName)
}

func TestModelEntityBatch(t *testing.T) {
	// Create a test batch
	batch := &models.ModelEntityBatch{
		MethodID:    5,
		EntityTexts: []string{"Credit Card", "SSN", "Phone Number"},
	}

	// Verify the fields
	assert.Equal(t, int64(5), batch.MethodID)
	assert.Len(t, batch.EntityTexts, 3)
	assert.Equal(t, "Credit Card", batch.EntityTexts[0])
	assert.Equal(t, "SSN", batch.EntityTexts[1])
	assert.Equal(t, "Phone Number", batch.EntityTexts[2])
}

func TestModelEntityDelete(t *testing.T) {
	// Create a test delete request
	deleteRequest := &models.ModelEntityDelete{
		IDs: []int64{1, 2, 3},
	}

	// Verify the fields
	assert.Len(t, deleteRequest.IDs, 3)
	assert.Equal(t, int64(1), deleteRequest.IDs[0])
	assert.Equal(t, int64(2), deleteRequest.IDs[1])
	assert.Equal(t, int64(3), deleteRequest.IDs[2])
}
