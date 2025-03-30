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
	assert.Equal(t, "RegexSearch", models.DetectionMethodRegexSearch)
	assert.Equal(t, "MLModel1", models.DetectionMethodMLModel1)
	assert.Equal(t, "MLModel2", models.DetectionMethodMLModel2)
	assert.Equal(t, "AIModel", models.DetectionMethodAIModel)
}

func TestDefaultDetectionMethods(t *testing.T) {
	// Get the default detection methods
	methods := models.DefaultDetectionMethods()

	// Verify the number of default methods
	assert.Len(t, methods, 5, "There should be 5 default detection methods")

	// Verify each method
	testCases := []struct {
		index         int
		expectedName  string
		expectedColor string
	}{
		{0, models.DetectionMethodManual, "#FF5733"},
		{1, models.DetectionMethodRegexSearch, "#33A8FF"},
		{2, models.DetectionMethodMLModel1, "#33FF57"},
		{3, models.DetectionMethodMLModel2, "#F033FF"},
		{4, models.DetectionMethodAIModel, "#FFFF33"},
	}

	for _, tc := range testCases {
		t.Run(tc.expectedName, func(t *testing.T) {
			method := methods[tc.index]
			assert.Equal(t, tc.expectedName, method.MethodName)
			assert.Equal(t, tc.expectedColor, method.HighlightColor)
		})
	}
}
