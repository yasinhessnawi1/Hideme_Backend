package models_test

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestSearchPattern_TableName(t *testing.T) {
	// Create a test search pattern
	pattern := &models.SearchPattern{
		ID:          1,
		SettingID:   100,
		PatternType: models.PatternType("regx"),
		PatternText: "\\d{4}-\\d{4}-\\d{4}-\\d{4}",
	}

	// Verify the table name
	tableName := pattern.TableName()
	assert.Equal(t, "search_patterns", tableName, "TableName should return the correct database table name")
}

func TestPatternTypeConstants(t *testing.T) {
	// Verify the pattern type constants
	assert.Equal(t, models.PatternType("ai_search"), models.AISearch)
	assert.Equal(t, models.PatternType("normal"), models.Normal)
	assert.Equal(t, models.PatternType("case_sensitive"), models.CaseSensitive)
}

func TestNewSearchPattern(t *testing.T) {
	// Test parameters
	settingID := int64(100)
	patternType := models.PatternType("regx")
	patternText := "\\d{3}-\\d{2}-\\d{4}" // SSN pattern

	// Create a new search pattern
	pattern := models.NewSearchPattern(settingID, patternType, patternText)

	// Verify the pattern was created correctly
	assert.NotNil(t, pattern, "NewSearchPattern should return a non-nil SearchPattern")
	assert.Equal(t, settingID, pattern.SettingID, "SearchPattern should have the provided setting ID")
	assert.Equal(t, patternType, pattern.PatternType, "SearchPattern should have the provided pattern type")
	assert.Equal(t, patternText, pattern.PatternText, "SearchPattern should have the provided pattern text")
	assert.Equal(t, int64(0), pattern.ID, "A new SearchPattern should have zero ID until saved to database")
}

func TestValidatePatternType(t *testing.T) {
	testCases := []struct {
		name        string
		patternType models.PatternType
		isValid     bool
	}{
		{"Valid AISearch", models.AISearch, true},
		{"Valid Normal", models.Normal, true},
		{"Valid CaseSensitive", models.CaseSensitive, true},
		{"Invalid Empty", "", false},
		{"Invalid Type", models.PatternType("Invalid"), false},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Validate the pattern type
			isValid := models.ValidatePatternType(tc.patternType)
			assert.Equal(t, tc.isValid, isValid)
		})
	}
}

func TestSearchPatternCreate(t *testing.T) {
	// Create a test create request
	createRequest := &models.SearchPatternCreate{
		PatternType: "ai_search",
		PatternText: "\\d{3}-\\d{2}-\\d{4}",
	}

	// Verify the fields
	assert.Equal(t, "ai_search", createRequest.PatternType)
	assert.Equal(t, "\\d{3}-\\d{2}-\\d{4}", createRequest.PatternText)
}

func TestSearchPatternUpdate(t *testing.T) {
	// Create a test update request
	updateRequest := &models.SearchPatternUpdate{
		PatternType: "normal",
		PatternText: "confidential",
	}

	// Verify the fields
	assert.Equal(t, "normal", updateRequest.PatternType)
	assert.Equal(t, "confidential", updateRequest.PatternText)

	// Test partial update with only pattern text
	partialUpdate := &models.SearchPatternUpdate{
		PatternText: "secret",
	}
	assert.Equal(t, "", partialUpdate.PatternType)
	assert.Equal(t, "secret", partialUpdate.PatternText)
}

func TestSearchPatternDelete(t *testing.T) {
	// Create a test delete request
	deleteRequest := &models.SearchPatternDelete{
		IDs: []int64{1, 2, 3},
	}

	// Verify the fields
	assert.Len(t, deleteRequest.IDs, 3)
	assert.Equal(t, int64(1), deleteRequest.IDs[0])
	assert.Equal(t, int64(2), deleteRequest.IDs[1])
	assert.Equal(t, int64(3), deleteRequest.IDs[2])
}
