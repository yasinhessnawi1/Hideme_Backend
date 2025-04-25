// Package models provides data structures and operations for the HideMe application.
// This file contains models related to ban list words that help reduce false positives
// during sensitive information detection.
package models

import (
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// BanListWord represents an individual banned word within a ban list.
// These words are excluded from detection to reduce false positives in the
// sensitive information identification process. Users can manage these
// lists to fine-tune detection accuracy for their specific needs.
type BanListWord struct {
	// ID is the unique identifier for this ban list word
	ID int64 `json:"id" db:"ban_word_id"`

	// BanID references the ban list to which this word belongs
	BanID int64 `json:"ban_id" db:"ban_id"`

	// Word contains the actual text to be excluded from detection
	Word string `json:"word" db:"word"`
}

// TableName returns the database table name for the BanListWord model.
// This method is used by ORM frameworks to determine where to persist this entity.
func (blw *BanListWord) TableName() string {
	return constants.TableBanListWords
}

// NewBanListWord creates a new BanListWord with the given ban ID and word.
//
// Parameters:
//   - banID: The ID of the ban list to which this word belongs
//   - word: The text to be excluded from detection
//
// Returns:
//   - A new BanListWord pointer with the specified ban ID and word
func NewBanListWord(banID int64, word string) *BanListWord {
	return &BanListWord{
		BanID: banID,
		Word:  word,
	}
}

// BanListWordBatch represents a batch of words to add to or remove from a ban list.
// This structure facilitates bulk operations on ban lists for more efficient updates.
type BanListWordBatch struct {
	// Words is a slice of strings to be added to or removed from a ban list
	// Each word must be non-empty and the slice must contain at least one word
	Words []string `json:"words" validate:"required,min=1,dive,required,min=1"`
}
