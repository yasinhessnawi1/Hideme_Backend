package models_test

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestDetectionMethod_TableName(t *testing.T) {
	// Create a test detection method
	method := &models.DetectionMethod{
		ID:             1,
		MethodName:     "Test Method",
		HighlightColor: "#FF5733",
	}

	// Verify the table name
	tableName := method.TableName()
	assert.Equal(t, "detection_methods", tableName, "TableName should return the correct database table name")
}

func TestDetectionMethodConstants(t *testing.T) {
	// Verify the predefined detection method constants
	assert.Equal(t, "Manual", models.DetectionMethodManual)
	assert.Equal(t, "Search", models.DetectionMethodSearch)
	assert.Equal(t, "AiSearch", models.DetectionMethodAiSearch)
	assert.Equal(t, "CaseSensitive", models.DetectionMethodCaseSensitive)
	assert.Equal(t, "Presidio", models.DetectionMethodMLModel1)
	assert.Equal(t, "Gliner", models.DetectionMethodMLModel2)
	assert.Equal(t, "Gemini", models.DetectionMethodAIModel)
}

func TestDefaultDetectionMethods(t *testing.T) {
	// Get the default detection methods
	methods := models.DefaultDetectionMethods()

	// Verify the number of default methods - this should be 8 to match the implementation
	assert.Len(t, methods, 8, "There should be 8 default detection methods")

	// Verify each method - adding the missing HideMeModel and adjusting indices
	testCases := []struct {
		index         int
		expectedName  string
		expectedColor string
	}{
		{0, models.DetectionMethodMLModel1, "#33FF57"},
		{1, models.DetectionMethodMLModel2, "#F033FF"},
		{2, models.DetectionMethodAIModel, "#FFFF33"},
		{3, models.DetectionMethodHideMeModel, "#33FF57"}, // Add the missing model
		{4, models.DetectionMethodAiSearch, "#33A8FF"},
		{5, models.DetectionMethodCaseSensitive, "#33A8FF"},
		{6, models.DetectionMethodSearch, "#33A8FF"},
		{7, models.DetectionMethodManual, "#FF5733"},
	}

	for _, tc := range testCases {
		t.Run(tc.expectedName, func(t *testing.T) {
			method := methods[tc.index]
			assert.Equal(t, tc.expectedName, method.MethodName)
			assert.Equal(t, tc.expectedColor, method.HighlightColor)
		})
	}
}
