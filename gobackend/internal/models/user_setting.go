// Package models provides data structures and operations for the HideMe application.
// This file contains models related to user preferences and configuration settings
// that control the behavior of document processing and interface presentation.
package models

import (
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// UserSetting represents user-specific configuration options for the HideMe application.
// It stores preferences for document processing and redaction behavior.
// These settings allow users to customize the application's functionality to their
// specific privacy requirements and operational workflows.
type UserSetting struct {
	// ID is the unique identifier for these settings
	ID int64 `json:"id" db:"setting_id"`

	// UserID references the user who owns these settings
	UserID int64 `json:"user_id" db:"user_id"`

	// RemoveImages determines whether images should be removed from processed documents
	// This enhances privacy by eliminating potentially sensitive visual information
	RemoveImages bool `json:"remove_images" db:"remove_images"`

	// Theme stores the user's preferred UI theme (e.g., "light", "dark", "system")
	Theme string `json:"theme" db:"theme"`

	// AutoProcessing enables automatic detection of sensitive information
	// when documents are uploaded without requiring explicit user action
	AutoProcessing bool `json:"auto_processing" db:"auto_processing"`

	// DetectionThreshold defines the confidence level required for AI/ML detection
	// Higher values increase precision but may miss some sensitive information
	// Lower values increase recall but may produce more false positives
	// Valid values range from 0.0 to 1.0, with 0.5 being the default
	DetectionThreshold float64 `json:"detection_threshold" db:"detection_threshold"`

	// UseBanlistForDetection determines whether the ban list should be
	// applied during detection to exclude specified terms
	UseBanlistForDetection bool `json:"use_banlist_for_detection" db:"use_banlist_for_detection"`

	// CreatedAt records when these settings were initially created
	CreatedAt time.Time `json:"created_at" db:"created_at"`

	// UpdatedAt records when these settings were last modified
	UpdatedAt time.Time `json:"updated_at" db:"updated_at"`
}

// NewUserSetting creates a new UserSetting instance with default values.
//
// Parameters:
//   - userID: The ID of the user who owns these settings
//
// Returns:
//   - A new UserSetting pointer with initialized fields and default values
//
// The default settings are optimized for privacy protection while maintaining
// usability, with security-conscious defaults like image removal and ban list usage.
func NewUserSetting(userID int64) *UserSetting {
	now := time.Now()
	return &UserSetting{
		UserID:                 userID,
		RemoveImages:           true,
		Theme:                  constants.ThemeSystem,
		DetectionThreshold:     0.50,
		UseBanlistForDetection: true,
		AutoProcessing:         true,
		CreatedAt:              now,
		UpdatedAt:              now,
	}
}

// TableName returns the database table name for the UserSetting model.
// This method is used by ORM frameworks to determine where to persist this entity.
func (us *UserSetting) TableName() string {
	return constants.TableUserSettings
}

// UserSettingsUpdate represents the data that can be updated for user settings.
// This structure validates settings update requests, allowing for partial
// updates where only some settings are modified.
type UserSettingsUpdate struct {
	// RemoveImages determines whether images should be removed from processed documents
	RemoveImages *bool `json:"remove_images" validate:"omitempty"`

	// Theme stores the user's preferred UI theme
	Theme *string `json:"theme"`

	// AutoProcessing enables automatic detection of sensitive information
	AutoProcessing *bool `json:"auto_processing"`

	// DetectionThreshold defines the confidence level required for AI/ML detection
	// Valid values range from 0.0 to 1.0
	DetectionThreshold *float64 `json:"detection_threshold" validate:"omitempty"`

	// UseBanlistForDetection determines whether the ban list should be applied during detection
	UseBanlistForDetection *bool `json:"use_banlist_for_detection" validate:"omitempty"`
}

// Apply updates the UserSetting with values from the update request.
//
// Parameters:
//   - update: A UserSettingsUpdate containing the fields to update
//
// The method only updates fields that are present in the update request,
// leaving other fields unchanged. This allows for partial updates of settings.
// The UpdatedAt timestamp is automatically updated to record the modification time.
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
	if update.DetectionThreshold != nil {
		s.DetectionThreshold = *update.DetectionThreshold
	}
	if update.UseBanlistForDetection != nil {
		s.UseBanlistForDetection = *update.UseBanlistForDetection
	}

	// Update the timestamp
	s.UpdatedAt = time.Now()
}
