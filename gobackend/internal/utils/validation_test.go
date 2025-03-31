package utils_test

import (
	"bytes"
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

type TestModel struct {
	Username string `json:"username" validate:"required,min=3,max=50"`
	Email    string `json:"email" validate:"required,email"`
	Password string `json:"password" validate:"required,min=8"`
}

func TestDecodeJSON(t *testing.T) {
	tests := []struct {
		name        string
		requestBody string
		wantErr     bool
		errContains string
	}{
		{
			name:        "Valid JSON",
			requestBody: `{"username":"john","email":"john@example.com","password":"password123"}`,
			wantErr:     false,
		},
		{
			name:        "Invalid JSON syntax",
			requestBody: `{"username":"john","email":john@example.com","password":"password123"}`,
			wantErr:     true,
			errContains: "malformed JSON",
		},
		{
			name:        "Empty request body",
			requestBody: "",
			wantErr:     true,
			errContains: "empty",
		},
		{
			name:        "Unknown field",
			requestBody: `{"username":"john","email":"john@example.com","password":"password123","unknown":"value"}`,
			wantErr:     true,
			errContains: "unknown field",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create request with JSON body
			var requestBody io.Reader
			if tt.requestBody != "" {
				requestBody = bytes.NewBufferString(tt.requestBody)
			}

			req := httptest.NewRequest("POST", "/", requestBody)
			req.Header.Set("Content-Type", "application/json")

			// Test object to decode into
			var model TestModel

			// Call the function being tested
			err := utils.DecodeJSON(req, &model)

			// Check error status
			if (err != nil) != tt.wantErr {
				t.Errorf("DecodeJSON() error = %v, wantErr %v", err, tt.wantErr)
				return
			}

			// If error is expected, check the error message
			if tt.wantErr && err != nil && tt.errContains != "" {
				if !strings.Contains(err.Error(), tt.errContains) {
					t.Errorf("Error message does not contain %q: %v", tt.errContains, err)
				}
			}

			// If no error, validate model data
			if err == nil {
				if model.Username != "john" {
					t.Errorf("Expected username 'john', got %v", model.Username)
				}
				if model.Email != "john@example.com" {
					t.Errorf("Expected email 'john@example.com', got %v", model.Email)
				}
				if model.Password != "password123" {
					t.Errorf("Expected password 'password123', got %v", model.Password)
				}
			}
		})
	}
}

func TestValidateStruct(t *testing.T) {
	tests := []struct {
		name        string
		model       TestModel
		wantErr     bool
		errContains string
		errField    string
	}{
		{
			name: "Valid model",
			model: TestModel{
				Username: "john",
				Email:    "john@example.com",
				Password: "password123",
			},
			wantErr: false,
		},
		{
			name: "Missing username",
			model: TestModel{
				Email:    "john@example.com",
				Password: "password123",
			},
			wantErr:     true,
			errContains: "required",
			errField:    "username",
		},
		{
			name: "Invalid email",
			model: TestModel{
				Username: "john",
				Email:    "invalid-email",
				Password: "password123",
			},
			wantErr:     true,
			errContains: "valid email",
			errField:    "email",
		},
		{
			name: "Password too short",
			model: TestModel{
				Username: "john",
				Email:    "john@example.com",
				Password: "pass",
			},
			wantErr:     true,
			errContains: "at least 8",
			errField:    "password",
		},
		{
			name: "Multiple validation errors",
			model: TestModel{
				Username: "jo", // Too short
				Email:    "invalid-email",
				Password: "pass", // Too short
			},
			wantErr:     true,
			errContains: "validation", // Generic error message for multiple errors
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Initialize validator
			utils.InitValidator()

			// Call the function being tested
			err := utils.ValidateStruct(tt.model)

			// Check error status
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateStruct() error = %v, wantErr %v", err, tt.wantErr)
				return
			}

			// If error is expected, check the error message and field
			if tt.wantErr && err != nil {
				// Convert to AppError if possible
				appErr, ok := err.(*utils.AppError)
				if !ok {
					t.Errorf("Expected AppError, got %T", err)
					return
				}

				// Check error message
				if tt.errContains != "" && !strings.Contains(appErr.Message, tt.errContains) {
					t.Errorf("Error message does not contain %q: %v", tt.errContains, appErr.Message)
				}

				// Check error field
				if tt.errField != "" && appErr.Field != tt.errField {
					t.Errorf("Error field: got %v want %v", appErr.Field, tt.errField)
				}
			}
		})
	}
}

func TestDecodeAndValidate(t *testing.T) {
	// Test both decoding and validation
	requestBody := `{"username":"j","email":"invalid-email","password":"pass"}`

	req := httptest.NewRequest("POST", "/", bytes.NewBufferString(requestBody))
	req.Header.Set("Content-Type", "application/json")

	var model TestModel

	// Call the function being tested
	err := utils.DecodeAndValidate(req, &model)

	// Should have validation error
	if err == nil {
		t.Errorf("DecodeAndValidate() should return error for invalid model")
	}
}

func TestIsValidEmail(t *testing.T) {
	tests := []struct {
		name  string
		email string
		want  bool
	}{
		{
			name:  "Valid email",
			email: "john@example.com",
			want:  true,
		},
		{
			name:  "Invalid email - no domain",
			email: "john@",
			want:  false,
		},
		{
			name:  "Invalid email - no @",
			email: "johnexample.com",
			want:  false,
		},
		{
			name:  "Invalid email - empty",
			email: "",
			want:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			utils.InitValidator()
			if got := utils.IsValidEmail(tt.email); got != tt.want {
				t.Errorf("IsValidEmail() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestValidateUsername(t *testing.T) {
	tests := []struct {
		name     string
		username string
		wantErr  bool
	}{
		{
			name:     "Valid username",
			username: "john123",
			wantErr:  false,
		},
		{
			name:     "Too short",
			username: "jo",
			wantErr:  true,
		},
		{
			name:     "Too long",
			username: strings.Repeat("a", 51),
			wantErr:  true,
		},
		{
			name:     "Invalid characters",
			username: "john@123",
			wantErr:  true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			utils.InitValidator()
			err := utils.ValidateUsername(tt.username)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidateUsername() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}

func TestValidatePassword(t *testing.T) {
	tests := []struct {
		name     string
		password string
		wantErr  bool
	}{
		{
			name:     "Valid password",
			password: "Password123!",
			wantErr:  false,
		},
		{
			name:     "Too short",
			password: "pass",
			wantErr:  true,
		},
		{
			name:     "Missing complexity",
			password: "12345678",
			wantErr:  true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			utils.InitValidator()
			err := utils.ValidatePassword(tt.password)
			if (err != nil) != tt.wantErr {
				t.Errorf("ValidatePassword() error = %v, wantErr %v", err, tt.wantErr)
			}
		})
	}
}
