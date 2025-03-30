package utils_test

import (
	"errors"
	"net/http"
	"testing"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

func TestNew(t *testing.T) {
	tests := []struct {
		name       string
		err        error
		statusCode int
		message    string
		wantMsg    string
	}{
		{
			name:       "Basic error",
			err:        errors.New("base error"),
			statusCode: http.StatusBadRequest,
			message:    "Error message",
			wantMsg:    "Error message",
		},
		{
			name:       "Internal server error",
			err:        errors.New("some internal error"),
			statusCode: http.StatusInternalServerError,
			message:    "Internal server error",
			wantMsg:    "Internal server error",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			appErr := utils.New(tt.err, tt.statusCode, tt.message)

			if appErr.Error() != tt.wantMsg {
				t.Errorf("New().Error() = %v, want %v", appErr.Error(), tt.wantMsg)
			}

			if appErr.StatusCode != tt.statusCode {
				t.Errorf("New().StatusCode = %v, want %v", appErr.StatusCode, tt.statusCode)
			}

			if appErr.Message != tt.message {
				t.Errorf("New().Message = %v, want %v", appErr.Message, tt.message)
			}

			if !errors.Is(appErr.Unwrap(), tt.err) {
				t.Errorf("New().Unwrap() = %v, want %v", appErr.Unwrap(), tt.err)
			}
		})
	}
}

func TestNewWithDevInfo(t *testing.T) {
	baseErr := errors.New("base error")
	appErr := utils.NewWithDevInfo(baseErr, http.StatusBadRequest, "Error message", "Developer info")

	if appErr.Error() != "Error message" {
		t.Errorf("NewWithDevInfo().Error() = %v, want %v", appErr.Error(), "Error message")
	}

	if appErr.DevInfo != "Developer info" {
		t.Errorf("NewWithDevInfo().DevInfo = %v, want %v", appErr.DevInfo, "Developer info")
	}
}

func TestNewValidationError(t *testing.T) {
	tests := []struct {
		name    string
		field   string
		message string
		want    string
	}{
		{
			name:    "Basic validation error",
			field:   "username",
			message: "Username is required",
			want:    "username: Username is required",
		},
		{
			name:    "Empty field",
			field:   "",
			message: "General validation error",
			want:    "General validation error",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			appErr := utils.NewValidationError(tt.field, tt.message)

			if appErr.Error() != tt.want {
				t.Errorf("NewValidationError().Error() = %v, want %v", appErr.Error(), tt.want)
			}

			if appErr.StatusCode != http.StatusBadRequest {
				t.Errorf("NewValidationError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusBadRequest)
			}

			if appErr.Field != tt.field {
				t.Errorf("NewValidationError().Field = %v, want %v", appErr.Field, tt.field)
			}

			if !errors.Is(appErr.Unwrap(), utils.ErrValidation) {
				t.Errorf("NewValidationError().Unwrap() = %v, want %v", appErr.Unwrap(), utils.ErrValidation)
			}
		})
	}
}

func TestNewBadRequestError(t *testing.T) {
	message := "Bad request message"
	appErr := utils.NewBadRequestError(message)

	if appErr.Error() != message {
		t.Errorf("NewBadRequestError().Error() = %v, want %v", appErr.Error(), message)
	}

	if appErr.StatusCode != http.StatusBadRequest {
		t.Errorf("NewBadRequestError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusBadRequest)
	}

	if !errors.Is(appErr.Unwrap(), utils.ErrBadRequest) {
		t.Errorf("NewBadRequestError().Unwrap() = %v, want %v", appErr.Unwrap(), utils.ErrBadRequest)
	}
}

func TestNewNotFoundError(t *testing.T) {
	tests := []struct {
		name         string
		resourceType string
		identifier   interface{}
		want         string
	}{
		{
			name:         "String identifier",
			resourceType: "User",
			identifier:   "abc123",
			want:         "User with identifier 'abc123' not found",
		},
		{
			name:         "Int identifier",
			resourceType: "Post",
			identifier:   42,
			want:         "Post with identifier '42' not found",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			appErr := utils.NewNotFoundError(tt.resourceType, tt.identifier)

			if appErr.Error() != tt.want {
				t.Errorf("NewNotFoundError().Error() = %v, want %v", appErr.Error(), tt.want)
			}

			if appErr.StatusCode != http.StatusNotFound {
				t.Errorf("NewNotFoundError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusNotFound)
			}

			if !errors.Is(appErr.Unwrap(), utils.ErrNotFound) {
				t.Errorf("NewNotFoundError().Unwrap() = %v, want %v", appErr.Unwrap(), utils.ErrNotFound)
			}
		})
	}
}

func TestIsNotFoundError(t *testing.T) {
	tests := []struct {
		name string
		err  error
		want bool
	}{
		{
			name: "Not found error",
			err:  utils.NewNotFoundError("User", 1),
			want: true,
		},
		{
			name: "Basic not found error",
			err:  utils.ErrNotFound,
			want: true,
		},
		{
			name: "Other app error",
			err:  utils.NewBadRequestError("Bad request"),
			want: false,
		},
		{
			name: "Standard error",
			err:  errors.New("standard error"),
			want: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := utils.IsNotFoundError(tt.err); got != tt.want {
				t.Errorf("IsNotFoundError() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestParseError(t *testing.T) {
	tests := []struct {
		name       string
		err        error
		wantStatus int
		wantType   error
	}{
		{
			name:       "AppError passthrough",
			err:        utils.NewValidationError("field", "message"),
			wantStatus: http.StatusBadRequest,
			wantType:   utils.ErrValidation,
		},
		{
			name:       "NotFound error",
			err:        utils.ErrNotFound,
			wantStatus: http.StatusNotFound,
			wantType:   utils.ErrNotFound,
		},
		{
			name:       "Unauthorized error",
			err:        utils.ErrUnauthorized,
			wantStatus: http.StatusUnauthorized,
			wantType:   utils.ErrUnauthorized,
		},
		{
			name:       "Forbidden error",
			err:        utils.ErrForbidden,
			wantStatus: http.StatusForbidden,
			wantType:   utils.ErrForbidden,
		},
		{
			name:       "Standard error",
			err:        errors.New("standard error"),
			wantStatus: http.StatusInternalServerError,
			wantType:   utils.ErrInternalServer,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			appErr := utils.ParseError(tt.err)

			if appErr.StatusCode != tt.wantStatus {
				t.Errorf("ParseError().StatusCode = %v, want %v", appErr.StatusCode, tt.wantStatus)
			}

			if !errors.Is(appErr.Unwrap(), tt.wantType) {
				t.Errorf("ParseError().Unwrap() = %v, want %v", appErr.Unwrap(), tt.wantType)
			}
		})
	}
}

func TestStatusCode(t *testing.T) {
	tests := []struct {
		name       string
		err        error
		wantStatus int
	}{
		{
			name:       "AppError",
			err:        utils.NewValidationError("field", "message"),
			wantStatus: http.StatusBadRequest,
		},
		{
			name:       "Standard error",
			err:        errors.New("standard error"),
			wantStatus: http.StatusInternalServerError,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := utils.StatusCode(tt.err); got != tt.wantStatus {
				t.Errorf("StatusCode() = %v, want %v", got, tt.wantStatus)
			}
		})
	}
}
