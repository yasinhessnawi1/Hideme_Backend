package service

import (
	"testing"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
)

// TestDatabaseService_ValidateTableAccess tests the ValidateTableAccess method
func TestDatabaseService_ValidateTableAccess(t *testing.T) {
	// Create the database service
	db := &database.Pool{}
	service := NewDatabaseService(db)

	// Define test cases
	tests := []struct {
		name        string
		table       string
		expectError bool
	}{
		{
			name:        "Allowed table",
			table:       "detection_methods",
			expectError: false,
		},
		{
			name:        "Disallowed table",
			table:       "users",
			expectError: true,
		},
		{
			name:        "Non-existent table",
			table:       "non_existent_table",
			expectError: true,
		},
	}

	// Run test cases
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			err := service.ValidateTableAccess(tc.table)

			if tc.expectError && err == nil {
				t.Errorf("Expected error, but got nil")
			}

			if !tc.expectError && err != nil {
				t.Errorf("Expected no error, but got: %v", err)
			}
		})
	}
}
