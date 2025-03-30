package models_test

import (
	"github.com/stretchr/testify/assert"
	"testing"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestNewUserSetting(t *testing.T) {
	// Test parameters
	userID := int64(123)

	// Create a new user setting
	setting := models.NewUserSetting(userID)

	// Check values
	if setting.UserID != userID {
		t.Errorf("Expected UserID = %d, got %d", userID, setting.UserID)
	}

	// RemoveImages should default to false
	if setting.RemoveImages {
		t.Error("Expected RemoveImages to default to false")
	}

	// Check created and updated times
	if setting.CreatedAt.IsZero() {
		t.Error("CreatedAt should not be zero")
	}

	if setting.UpdatedAt.IsZero() {
		t.Error("UpdatedAt should not be zero")
	}

	// CreatedAt and UpdatedAt should be the same for a new setting
	if !setting.CreatedAt.Equal(setting.UpdatedAt) {
		t.Errorf("CreatedAt (%v) should equal UpdatedAt (%v)", setting.CreatedAt, setting.UpdatedAt)
	}
}

func TestUserSetting_TableName(t *testing.T) {
	setting := &models.UserSetting{}

	tableName := setting.TableName()

	if tableName != "user_settings" {
		t.Errorf("Expected TableName = %s, got %s", "user_settings", tableName)
	}
}

func TestUserSetting_Apply(t *testing.T) {
	// Create a setting with initial values
	setting := &models.UserSetting{
		ID:           123,
		UserID:       456,
		RemoveImages: false,
		CreatedAt:    time.Now().Add(-1 * time.Hour), // 1 hour ago
		UpdatedAt:    time.Now().Add(-1 * time.Hour), // 1 hour ago
	}

	// Create an update
	removeImages := true
	update := &models.UserSettingsUpdate{
		RemoveImages: &removeImages,
	}

	// Store the original updated time
	originalUpdatedAt := setting.UpdatedAt

	// Apply the update after a short delay
	time.Sleep(10 * time.Millisecond) // Ensure updated time will be different
	setting.Apply(update)

	// Check that the value was updated
	if !setting.RemoveImages {
		t.Error("Expected RemoveImages to be updated to true")
	}

	// Check that UpdatedAt was updated
	if !setting.UpdatedAt.After(originalUpdatedAt) {
		t.Error("Expected UpdatedAt to be updated")
	}

	// Create an update with nil values (should not change)
	setting.RemoveImages = true
	update = &models.UserSettingsUpdate{
		RemoveImages: nil,
	}

	// Store the updated time
	originalUpdatedAt = setting.UpdatedAt

	// Apply the update after a short delay
	time.Sleep(10 * time.Millisecond)
	setting.Apply(update)

	// Check that the value was not changed
	if !setting.RemoveImages {
		t.Error("Expected RemoveImages to remain true")
	}

	// Check that UpdatedAt was still updated
	if !setting.UpdatedAt.After(originalUpdatedAt) {
		t.Error("Expected UpdatedAt to be updated even with no changes")
	}
}

func TestUserSettingsUpdate(t *testing.T) {
	// Create test cases
	testCases := []struct {
		name           string
		update         *models.UserSettingsUpdate
		initialSetting *models.UserSetting
		expectedImages bool
	}{
		{
			name: "Update RemoveImages to true",
			update: &models.UserSettingsUpdate{
				RemoveImages: boolPtr(true),
			},
			initialSetting: &models.UserSetting{
				ID:           1,
				UserID:       100,
				RemoveImages: false,
				CreatedAt:    time.Now().Add(-24 * time.Hour),
				UpdatedAt:    time.Now().Add(-24 * time.Hour),
			},
			expectedImages: true,
		},
		{
			name: "Update RemoveImages to false",
			update: &models.UserSettingsUpdate{
				RemoveImages: boolPtr(false),
			},
			initialSetting: &models.UserSetting{
				ID:           1,
				UserID:       100,
				RemoveImages: true,
				CreatedAt:    time.Now().Add(-24 * time.Hour),
				UpdatedAt:    time.Now().Add(-24 * time.Hour),
			},
			expectedImages: false,
		},
		{
			name: "No RemoveImages update",
			update: &models.UserSettingsUpdate{
				RemoveImages: nil,
			},
			initialSetting: &models.UserSetting{
				ID:           1,
				UserID:       100,
				RemoveImages: true,
				CreatedAt:    time.Now().Add(-24 * time.Hour),
				UpdatedAt:    time.Now().Add(-24 * time.Hour),
			},
			expectedImages: true, // Should remain unchanged
		},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Record initial timestamp
			initialUpdatedAt := tc.initialSetting.UpdatedAt

			// Apply the update
			now := time.Now()
			tc.initialSetting.Apply(tc.update)

			// Verify the updates were applied correctly
			assert.Equal(t, tc.expectedImages, tc.initialSetting.RemoveImages, "RemoveImages should be updated correctly")
			assert.WithinDuration(t, now, tc.initialSetting.UpdatedAt, time.Second, "UpdatedAt should be updated to current time")
			assert.NotEqual(t, initialUpdatedAt, tc.initialSetting.UpdatedAt, "UpdatedAt timestamp should be changed")
		})
	}
}

// Helper function to create a pointer to a bool
func boolPtr(b bool) *bool {
	return &b
}
