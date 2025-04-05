package models

import (
	"time"
)

// UserSetting represents user-specific configuration options for the HideMe application.
// It stores preferences for document processing and redaction behavior.
type UserSetting struct {
	ID             int64     `json:"id" db:"setting_id"`
	UserID         int64     `json:"user_id" db:"user_id"`
	RemoveImages   bool      `json:"remove_images" db:"remove_images"`
	Theme          string    `json:"theme" db:"theme"`
	AutoProcessing bool      `json:"auto_processing" db:"auto_processing"`
	CreatedAt      time.Time `json:"created_at" db:"created_at"`
	UpdatedAt      time.Time `json:"updated_at" db:"updated_at"`
}

// NewUserSetting creates a new UserSetting instance with default values.
func NewUserSetting(userID int64) *UserSetting {
	now := time.Now()
	return &UserSetting{
		UserID:         userID,
		RemoveImages:   true,
		Theme:          "system",
		AutoProcessing: true,
		CreatedAt:      now,
		UpdatedAt:      now,
	}
}

// TableName returns the database table name for the UserSetting model.
func (us *UserSetting) TableName() string {
	return "user_settings"
}

// UserSettingsUpdate represents the data that can be updated for user settings.
type UserSettingsUpdate struct {
	RemoveImages   *bool   `json:"remove_images" validate:"omitempty"`
	Theme          *string `json:"theme"`
	AutoProcessing *bool   `json:"auto_processing"`
}

// Apply updates the UserSetting with values from the update request.
func (s *UserSetting) Apply(update *UserSettingsUpdate) {
	if update.RemoveImages != nil {
		s.RemoveImages = *update.RemoveImages
	}
	if update.Theme != nil {
		s.Theme = *update.Theme
	}
	if update.AutoProcessing != nil {
		s.AutoProcessing = *update.AutoProcessing
	}
}
