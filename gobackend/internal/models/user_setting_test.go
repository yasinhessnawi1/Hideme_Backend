package models_test

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestUserSetting_TableName(t *testing.T) {
	// Create a test user setting
	setting := &models.UserSetting{
		ID:                     1,
		UserID:                 100,
		RemoveImages:           true,
		Theme:                  "dark",
		AutoProcessing:         true,
		DetectionThreshold:     0.75,
		UseBanlistForDetection: true,
		CreatedAt:              time.Now(),
		UpdatedAt:              time.Now(),
	}

	// Verify the table name
	tableName := setting.TableName()
	assert.Equal(t, "user_settings", tableName, "TableName should return the correct database table name")
}

func TestNewUserSetting(t *testing.T) {
	// Test parameters
	userID := int64(100)

	// Create a new user setting
	now := time.Now()
	setting := models.NewUserSetting(userID)

	// Verify default values were set correctly
	assert.NotNil(t, setting, "NewUserSetting should return a non-nil UserSetting")
	assert.Equal(t, userID, setting.UserID, "UserSetting should have the provided user ID")
	assert.Equal(t, true, setting.RemoveImages, "RemoveImages should default to true")
	assert.Equal(t, "system", setting.Theme, "Theme should default to 'system'")
	assert.Equal(t, true, setting.AutoProcessing, "AutoProcessing should default to true")
	assert.Equal(t, 0.50, setting.DetectionThreshold, "DetectionThreshold should default to 0.50")
	assert.Equal(t, true, setting.UseBanlistForDetection, "UseBanlistForDetection should default to true")
	assert.WithinDuration(t, now, setting.CreatedAt, time.Second, "CreatedAt should be set to current time")
	assert.WithinDuration(t, now, setting.UpdatedAt, time.Second, "UpdatedAt should be set to current time")
	assert.Equal(t, int64(0), setting.ID, "A new UserSetting should have zero ID until saved to database")
}

func TestUserSetting_Apply(t *testing.T) {
	// Setup test cases
	testCases := []struct {
		name           string
		update         *models.UserSettingsUpdate
		expectedValues map[string]interface{}
	}{
		{
			name: "Update RemoveImages",
			update: &models.UserSettingsUpdate{
				RemoveImages: getBoolPtr(false),
			},
			expectedValues: map[string]interface{}{
				"RemoveImages": false,
			},
		},
		{
			name: "Update Theme",
			update: &models.UserSettingsUpdate{
				Theme: getStringPtr("dark"),
			},
			expectedValues: map[string]interface{}{
				"Theme": "dark",
			},
		},
		{
			name: "Update AutoProcessing",
			update: &models.UserSettingsUpdate{
				AutoProcessing: getBoolPtr(false),
			},
			expectedValues: map[string]interface{}{
				"AutoProcessing": false,
			},
		},
		{
			name: "Update DetectionThreshold",
			update: &models.UserSettingsUpdate{
				DetectionThreshold: getFloat64Ptr(0.85),
			},
			expectedValues: map[string]interface{}{
				"DetectionThreshold": 0.85,
			},
		},
		{
			name: "Update UseBanlistForDetection",
			update: &models.UserSettingsUpdate{
				UseBanlistForDetection: getBoolPtr(false),
			},
			expectedValues: map[string]interface{}{
				"UseBanlistForDetection": false,
			},
		},
		{
			name: "Update multiple fields",
			update: &models.UserSettingsUpdate{
				RemoveImages:           getBoolPtr(false),
				Theme:                  getStringPtr("light"),
				AutoProcessing:         getBoolPtr(false),
				DetectionThreshold:     getFloat64Ptr(0.90),
				UseBanlistForDetection: getBoolPtr(false),
			},
			expectedValues: map[string]interface{}{
				"RemoveImages":           false,
				"Theme":                  "light",
				"AutoProcessing":         false,
				"DetectionThreshold":     0.90,
				"UseBanlistForDetection": false,
			},
		},
		{
			name:           "Update with nil values (should not change)",
			update:         &models.UserSettingsUpdate{},
			expectedValues: map[string]interface{}{}, // No changes expected
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Create a base setting with default values
			setting := models.NewUserSetting(100)

			// Apply the update
			setting.Apply(tc.update)

			// Verify all expected values
			for field, expected := range tc.expectedValues {
				switch field {
				case "RemoveImages":
					assert.Equal(t, expected, setting.RemoveImages)
				case "Theme":
					assert.Equal(t, expected, setting.Theme)
				case "AutoProcessing":
					assert.Equal(t, expected, setting.AutoProcessing)
				case "DetectionThreshold":
					assert.Equal(t, expected, setting.DetectionThreshold)
				case "UseBanlistForDetection":
					assert.Equal(t, expected, setting.UseBanlistForDetection)
				}
			}
		})
	}
}

func TestUserSettingsUpdate(t *testing.T) {
	// Test creating a UserSettingsUpdate with all fields
	removeImages := true
	theme := "dark"
	autoProcessing := false
	detectionThreshold := 0.75
	useBanlistForDetection := false

	update := &models.UserSettingsUpdate{
		RemoveImages:           &removeImages,
		Theme:                  &theme,
		AutoProcessing:         &autoProcessing,
		DetectionThreshold:     &detectionThreshold,
		UseBanlistForDetection: &useBanlistForDetection,
	}

	// Verify all fields are set correctly
	assert.NotNil(t, update.RemoveImages)
	assert.Equal(t, removeImages, *update.RemoveImages)
	assert.NotNil(t, update.Theme)
	assert.Equal(t, theme, *update.Theme)
	assert.NotNil(t, update.AutoProcessing)
	assert.Equal(t, autoProcessing, *update.AutoProcessing)
	assert.NotNil(t, update.DetectionThreshold)
	assert.Equal(t, detectionThreshold, *update.DetectionThreshold)
	assert.NotNil(t, update.UseBanlistForDetection)
	assert.Equal(t, useBanlistForDetection, *update.UseBanlistForDetection)
}

func TestUserSetting_EmptyUpdateHandling(t *testing.T) {
	// Create a setting with specific values
	setting := &models.UserSetting{
		ID:                     1,
		UserID:                 100,
		RemoveImages:           true,
		Theme:                  "dark",
		AutoProcessing:         true,
		DetectionThreshold:     0.75,
		UseBanlistForDetection: true,
		CreatedAt:              time.Now(),
		UpdatedAt:              time.Now(),
	}

	// Store original values
	originalValues := map[string]interface{}{
		"RemoveImages":           setting.RemoveImages,
		"Theme":                  setting.Theme,
		"AutoProcessing":         setting.AutoProcessing,
		"DetectionThreshold":     setting.DetectionThreshold,
		"UseBanlistForDetection": setting.UseBanlistForDetection,
	}

	// Apply an empty update
	emptyUpdate := &models.UserSettingsUpdate{}
	setting.Apply(emptyUpdate)

	// Verify nothing changed
	assert.Equal(t, originalValues["RemoveImages"], setting.RemoveImages)
	assert.Equal(t, originalValues["Theme"], setting.Theme)
	assert.Equal(t, originalValues["AutoProcessing"], setting.AutoProcessing)
	assert.Equal(t, originalValues["DetectionThreshold"], setting.DetectionThreshold)
	assert.Equal(t, originalValues["UseBanlistForDetection"], setting.UseBanlistForDetection)
}

// Helper functions for creating pointers
func getBoolPtr(v bool) *bool {
	return &v
}

func getStringPtr(v string) *string {
	return &v
}

func getFloat64Ptr(v float64) *float64 {
	return &v
}
