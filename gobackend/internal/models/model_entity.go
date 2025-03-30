package models

// ModelEntity represents predefined entities associated with specific detection methods.
// These are used by machine learning and AI models for identifying sensitive information.
type ModelEntity struct {
	ID         int64  `json:"id" db:"model_entity_id"`
	SettingID  int64  `json:"setting_id" db:"setting_id"`
	MethodID   int64  `json:"method_id" db:"method_id"`
	EntityText string `json:"entity_text" db:"entity_text"`
}

// TableName returns the database table name for the ModelEntity model.
func (me *ModelEntity) TableName() string {
	return "model_entities"
}

// NewModelEntity creates a new ModelEntity with the given parameters.
func NewModelEntity(settingID, methodID int64, entityText string) *ModelEntity {
	return &ModelEntity{
		SettingID:  settingID,
		MethodID:   methodID,
		EntityText: entityText,
	}
}

// ModelEntityWithMethod represents a model entity with its associated detection method.
// This is a convenience struct for API responses that need method information.
type ModelEntityWithMethod struct {
	ModelEntity
	MethodName string `json:"method_name"`
}

// ModelEntityBatch represents a batch of model entities for bulk operations.
type ModelEntityBatch struct {
	MethodID    int64    `json:"method_id" validate:"required"`
	EntityTexts []string `json:"entity_texts" validate:"required,min=1,dive,required"`
}

// ModelEntityDelete represents a request to delete specific model entities.
type ModelEntityDelete struct {
	IDs []int64 `json:"ids" validate:"required,min=1,dive,required,min=1"`
}
