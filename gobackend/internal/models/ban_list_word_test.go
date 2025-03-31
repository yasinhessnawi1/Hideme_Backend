package models_test

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestBanListWord_TableName(t *testing.T) {
	// Create a test ban list word
	banListWord := &models.BanListWord{
		ID:    1,
		BanID: 100,
		Word:  "test",
	}

	// Verify the table name
	tableName := banListWord.TableName()
	assert.Equal(t, "ban_list_words", tableName, "TableName should return the correct database table name")
}

func TestNewBanListWord(t *testing.T) {
	// Test parameters
	banID := int64(999)
	word := "sensitive-data"

	// Create a new ban list word
	banListWord := models.NewBanListWord(banID, word)

	// Verify the ban list word was created correctly
	assert.NotNil(t, banListWord, "NewBanListWord should return a non-nil BanListWord")
	assert.Equal(t, banID, banListWord.BanID, "BanListWord should have the provided ban ID")
	assert.Equal(t, word, banListWord.Word, "BanListWord should have the provided word")
	assert.Equal(t, int64(0), banListWord.ID, "A new BanListWord should have zero ID until saved to database")
}

func TestBanListWordBatch(t *testing.T) {
	// Create a test instance with words
	batch := &models.BanListWordBatch{
		Words: []string{"test", "example", "keyword"},
	}

	// Verify the fields
	assert.NotNil(t, batch, "BanListWordBatch should be created successfully")
	assert.Len(t, batch.Words, 3, "BanListWordBatch should have the correct number of words")
	assert.Equal(t, "test", batch.Words[0])
	assert.Equal(t, "example", batch.Words[1])
	assert.Equal(t, "keyword", batch.Words[2])

	// Test empty batch
	emptyBatch := &models.BanListWordBatch{
		Words: []string{},
	}
	assert.Empty(t, emptyBatch.Words, "Empty BanListWordBatch should have no words")
}
