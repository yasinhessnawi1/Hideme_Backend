// Package models provides data structures and operations for the HideMe application.
// This file contains models for settings export and import functionality, allowing
// users to backup, transfer, and restore their personalized configurations.
package models

import "time"

// SettingsExport represents the complete set of user settings for export/import.
// This comprehensive structure captures all user-specific configuration elements
// to enable complete backup and restoration of settings across environments or accounts.
// The export/import feature allows users to maintain consistent configurations
// and share standardized settings across teams or organizations.
type SettingsExport struct {
	// UserID identifies the user who owns these settings
	UserID int64 `json:"user_id"`

	// ExportDate records when this export was created
	ExportDate time.Time `json:"export_date"`

	// GeneralSettings contains the user's core application preferences
	GeneralSettings *UserSetting `json:"general_settings"`

	// BanList contains the user's list of words excluded from detection
	BanList *BanListWithWords `json:"ban_list"`

	// SearchPatterns contains the user's custom search patterns for detection
	SearchPatterns []*SearchPattern `json:"search_patterns"`

	// ModelEntities contains the user's custom entities for ML/AI detection
	// Each entity includes its associated detection method for completeness
	ModelEntities []*ModelEntityWithMethod `json:"model_entities"`
}
