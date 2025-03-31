package models_test

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestBanList_TableName(t *testing.T) {
	// Create a test ban list
	banList := &models.BanList{
		ID:        1,
		SettingID: 100,
	}

	// Verify the table name
	tableName := banList.TableName()
	assert.Equal(t, "ban_lists", tableName, "TableName should return the correct database table name")
}

func TestNewBanList(t *testing.T) {
	// Test parameters
	settingID := int64(999)

	// Create a new ban list
	banList := models.NewBanList(settingID)

	// Verify the ban list was created correctly
	assert.NotNil(t, banList, "NewBanList should return a non-nil BanList")
	assert.Equal(t, settingID, banList.SettingID, "BanList should have the provided setting ID")
	assert.Equal(t, int64(0), banList.ID, "A new BanList should have zero ID until saved to database")
}

func TestBanListWithWords(t *testing.T) {
	// Create a test instance
	banListWithWords := &models.BanListWithWords{
		ID:    123,
		Words: []string{"test", "example", "sensitive"},
	}

	// Verify the fields
	assert.Equal(t, int64(123), banListWithWords.ID)
	assert.Len(t, banListWithWords.Words, 3)
	assert.Equal(t, "test", banListWithWords.Words[0])
	assert.Equal(t, "example", banListWithWords.Words[1])
	assert.Equal(t, "sensitive", banListWithWords.Words[2])
}
