// Package models provides data structures and operations for the HideMe application.
// This file contains models related to ban lists that help users exclude specific words
// from detection to reduce false positives.
package models

import (
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// BanList represents a collection of words to exclude from detection.
// The ban list is associated with a specific user's settings and helps
// customize the sensitivity of detection algorithms to the user's needs.
// Words in the ban list are ignored during detection to reduce false positives.
type BanList struct {
	// ID is the unique identifier for this ban list
	ID int64 `json:"id" db:"ban_id"`

	// SettingID references the user settings to which this ban list belongs
	SettingID int64 `json:"setting_id" db:"setting_id"`
}

// TableName returns the database table name for the BanList model.
// This method is used by ORM frameworks to determine where to persist this entity.
func (bl *BanList) TableName() string {
	return constants.TableBanLists
}

// NewBanList creates a new BanList with the given setting ID.
//
// Parameters:
//   - settingID: The ID of the user settings to which this ban list belongs
//
// Returns:
//   - A new BanList pointer associated with the specified user settings
//
// The actual banned words are stored separately in the BanListWord table,
// linked to this ban list via their BanID field.
func NewBanList(settingID int64) *BanList {
	return &BanList{
		SettingID: settingID,
	}
}

// BanListWithWords represents a ban list with its associated banned words.
// This is a convenience struct for API responses, combining the ban list
// with all its associated words for easier client-side processing.
type BanListWithWords struct {
	// ID is the unique identifier for this ban list
	ID int64 `json:"id"`

	// Words is a slice of banned words associated with this ban list
	Words []string `json:"words"`
}
