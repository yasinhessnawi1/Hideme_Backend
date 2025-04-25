package models

import (
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// BanListWord represents an individual banned word within a ban list.
// These words are excluded from detection to reduce false positives.
type BanListWord struct {
	ID    int64  `json:"id" db:"ban_word_id"`
	BanID int64  `json:"ban_id" db:"ban_id"`
	Word  string `json:"word" db:"word"`
}

// TableName returns the database table name for the BanListWord model.
func (blw *BanListWord) TableName() string {
	return constants.TableBanListWords
}

// NewBanListWord creates a new BanListWord with the given ban ID and word.
func NewBanListWord(banID int64, word string) *BanListWord {
	return &BanListWord{
		BanID: banID,
		Word:  word,
	}
}

// BanListWordBatch represents a batch of words to add to or remove from a ban list.
type BanListWordBatch struct {
	Words []string `json:"words" validate:"required,min=1,dive,required,min=1"`
}
