// Package models provides data structures and operations for the HideMe application.
// This file contains models related to predefined entities that should be detected
// by specific machine learning and AI models during document processing.
package models

import (
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// ModelEntity represents predefined entities associated with specific detection methods.
// These are used by machine learning and AI models for identifying sensitive information.
// ModelEntities allow users to define custom entities that should be detected by
// specific ML/AI detection methods, enhancing the accuracy of sensitive information detection.
type ModelEntity struct {
	// ID is the unique identifier for this model entity
	ID int64 `json:"id" db:"model_entity_id"`

	// SettingID references the user settings to which this entity belongs
	SettingID int64 `json:"setting_id" db:"setting_id"`

	// MethodID references the detection method associated with this entity
	MethodID int64 `json:"method_id" db:"method_id"`

	// EntityText contains the actual text to be detected by the specified method
	// This might include names, terms, or patterns specific to the user's needs
	EntityText string `json:"entity_text" db:"entity_text"`
}

// TableName returns the database table name for the ModelEntity model.
// This method is used by ORM frameworks to determine where to persist this entity.
func (me *ModelEntity) TableName() string {
	return constants.TableModelEntities
}

// NewModelEntity creates a new ModelEntity with the given parameters.
//
// Parameters:
//   - settingID: The ID of the user settings to which this entity belongs
//   - methodID: The ID of the detection method to be used for this entity
//   - entityText: The text to be detected by the specified method
//
// Returns:
//   - A new ModelEntity pointer with the specified parameters
//
// Model entities allow for customization of detection algorithms to focus on
// specific sensitive information relevant to the user's context.
func NewModelEntity(settingID, methodID int64, entityText string) *ModelEntity {
	return &ModelEntity{
		SettingID:  settingID,
		MethodID:   methodID,
		EntityText: entityText,
	}
}

// ModelEntityWithMethod represents a model entity with its associated detection method.
// This is a convenience struct for API responses that need method information,
// reducing the need for separate queries to retrieve method details.
type ModelEntityWithMethod struct {
	ModelEntity

	// MethodName is the name of the detection method associated with this entity
	MethodName string `json:"method_name"`
}

// ModelEntityBatch represents a batch of model entities for bulk operations.
// This structure facilitates efficient creation of multiple model entities
// in a single operation, improving performance for large-scale configurations.
type ModelEntityBatch struct {
	// MethodID is the detection method to be used for all entities in this batch
	MethodID int64 `json:"method_id" validate:"required"`

	// EntityTexts contains the texts to be detected by the specified method
	// Must contain at least one entity text
	EntityTexts []string `json:"entity_texts" validate:"required,min=1,dive,required"`
}

// ModelEntityDelete represents a request to delete specific model entities.
// This structure validates delete operations to ensure proper request format.
type ModelEntityDelete struct {
	// IDs contains the unique identifiers of the model entities to delete
	// Must contain at least one valid ID
	IDs []int64 `json:"ids" validate:"required,min=1,dive,required,min=1"`
}
