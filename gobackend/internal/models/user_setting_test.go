package models_test

import (
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"testing"
)

func TestNewUserSetting(t *testing.T) {

}

func TestUserSetting_TableName(t *testing.T) {
	setting := &models.UserSetting{}

	tableName := setting.TableName()

	if tableName != "user_settings" {
		t.Errorf("Expected TableName = %s, got %s", "user_settings", tableName)
	}
}

func TestUserSetting_Apply(t *testing.T) {

}

func TestUserSettingsUpdate(t *testing.T) {

}

// Helper function to create a pointer to a bool
func boolPtr(b bool) *bool {
	return &b
}
