package utils_test

import (
	"database/sql"
	"errors"
	"net/http"
	"testing"

	"github.com/lib/pq"
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

func TestNewUnauthorizedError(t *testing.T) {
	tests := []struct {
		name    string
		message string
		want    string
	}{
		{
			name:    "With message",
			message: "Custom unauthorized message",
			want:    "Custom unauthorized message",
		},
		{
			name:    "Empty message",
			message: "",
			want:    "Authentication required",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			appErr := utils.NewUnauthorizedError(tt.message)

			if appErr.Error() != tt.want {
				t.Errorf("NewUnauthorizedError().Error() = %v, want %v", appErr.Error(), tt.want)
			}

			if appErr.StatusCode != http.StatusUnauthorized {
				t.Errorf("NewUnauthorizedError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusUnauthorized)
			}

			if !errors.Is(appErr.Unwrap(), utils.ErrUnauthorized) {
				t.Errorf("NewUnauthorizedError().Unwrap() = %v, want %v", appErr.Unwrap(), utils.ErrUnauthorized)
			}
		})
	}
}

func TestNewForbiddenError(t *testing.T) {
	tests := []struct {
		name    string
		message string
		want    string
	}{
		{
			name:    "With message",
			message: "Custom forbidden message",
			want:    "Custom forbidden message",
		},
		{
			name:    "Empty message",
			message: "",
			want:    "You don't have permission to access this resource",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			appErr := utils.NewForbiddenError(tt.message)

			if appErr.Error() != tt.want {
				t.Errorf("NewForbiddenError().Error() = %v, want %v", appErr.Error(), tt.want)
			}

			if appErr.StatusCode != http.StatusForbidden {
				t.Errorf("NewForbiddenError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusForbidden)
			}

			if !errors.Is(appErr.Unwrap(), utils.ErrForbidden) {
				t.Errorf("NewForbiddenError().Unwrap() = %v, want %v", appErr.Unwrap(), utils.ErrForbidden)
			}
		})
	}
}

func TestNewInternalServerError(t *testing.T) {
	baseErr := errors.New("internal error")
	appErr := utils.NewInternalServerError(baseErr)

	if appErr.Error() != "An internal server error occurred" {
		t.Errorf("NewInternalServerError().Error() = %v, want %v", appErr.Error(), "An internal server error occurred")
	}

	if appErr.StatusCode != http.StatusInternalServerError {
		t.Errorf("NewInternalServerError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusInternalServerError)
	}

	if !errors.Is(appErr.Unwrap(), utils.ErrInternalServer) {
		t.Errorf("NewInternalServerError().Unwrap() = %v, want %v", appErr.Unwrap(), utils.ErrInternalServer)
	}

	if appErr.DevInfo != baseErr.Error() {
		t.Errorf("NewInternalServerError().DevInfo = %v, want %v", appErr.DevInfo, baseErr.Error())
	}

	// Test with nil error
	nilErr := utils.NewInternalServerError(nil)
	if nilErr.DevInfo != "" {
		t.Errorf("NewInternalServerError(nil).DevInfo = %v, want empty string", nilErr.DevInfo)
	}
}

func TestNewInvalidCredentialsError(t *testing.T) {
	appErr := utils.NewInvalidCredentialsError()

	if appErr.Error() != "Invalid username or password" {
		t.Errorf("NewInvalidCredentialsError().Error() = %v, want %v", appErr.Error(), "Invalid username or password")
	}

	if appErr.StatusCode != http.StatusUnauthorized {
		t.Errorf("NewInvalidCredentialsError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusUnauthorized)
	}

	if !errors.Is(appErr.Unwrap(), utils.ErrInvalidCredentials) {
		t.Errorf("NewInvalidCredentialsError().Unwrap() = %v, want %v", appErr.Unwrap(), utils.ErrInvalidCredentials)
	}
}

func TestNewExpiredTokenError(t *testing.T) {
	appErr := utils.NewExpiredTokenError()

	if appErr.Error() != "Authentication token has expired" { // Updated expected message
		t.Errorf("NewExpiredTokenError().Error() = %v, want %v", appErr.Error(), "Authentication token has expired")
	}

	if appErr.StatusCode != http.StatusUnauthorized {
		t.Errorf("NewExpiredTokenError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusUnauthorized)
	}

	if !errors.Is(appErr.Unwrap(), utils.ErrExpiredToken) {
		t.Errorf("NewExpiredTokenError().Unwrap() = %v, want %v", appErr.Unwrap(), utils.ErrExpiredToken)
	}
}

func TestNewInvalidTokenError(t *testing.T) {
	appErr := utils.NewInvalidTokenError()

	if appErr.Error() != "Invalid token" {
		t.Errorf("NewInvalidTokenError().Error() = %v, want %v", appErr.Error(), "Invalid token")
	}

	if appErr.StatusCode != http.StatusUnauthorized {
		t.Errorf("NewInvalidTokenError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusUnauthorized)
	}

	if !errors.Is(appErr.Unwrap(), utils.ErrInvalidToken) {
		t.Errorf("NewInvalidTokenError().Unwrap() = %v, want %v", appErr.Unwrap(), utils.ErrInvalidToken)
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

func TestIsDuplicateError(t *testing.T) {
	tests := []struct {
		name string
		err  error
		want bool
	}{
		{
			name: "Duplicate error",
			err:  utils.NewDuplicateError("User", "email", "test@example.com"),
			want: true,
		},
		{
			name: "Basic duplicate error",
			err:  utils.ErrDuplicate,
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
			if got := utils.IsDuplicateError(tt.err); got != tt.want {
				t.Errorf("IsDuplicateError() = %v, want %v", got, tt.want)
			}
		})
	}
}

func TestIsValidationError(t *testing.T) {
	tests := []struct {
		name string
		err  error
		want bool
	}{
		{
			name: "Validation error",
			err:  utils.NewValidationError("field", "message"),
			want: true,
		},
		{
			name: "Basic validation error",
			err:  utils.ErrValidation,
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
			if got := utils.IsValidationError(tt.err); got != tt.want {
				t.Errorf("IsValidationError() = %v, want %v", got, tt.want)
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
			name:       "Bad request error",
			err:        utils.ErrBadRequest,
			wantStatus: http.StatusBadRequest,
			wantType:   utils.ErrBadRequest,
		},
		{
			name:       "Validation error",
			err:        utils.ErrValidation,
			wantStatus: http.StatusBadRequest,
			wantType:   utils.ErrValidation,
		},
		{
			name:       "Duplicate error",
			err:        utils.ErrDuplicate,
			wantStatus: http.StatusConflict,
			wantType:   utils.ErrDuplicate,
		},
		{
			name:       "Invalid credentials error",
			err:        utils.ErrInvalidCredentials,
			wantStatus: http.StatusUnauthorized,
			wantType:   utils.ErrInvalidCredentials,
		},
		{
			name:       "Expired token error",
			err:        utils.ErrExpiredToken,
			wantStatus: http.StatusUnauthorized,
			wantType:   utils.ErrExpiredToken,
		},
		{
			name:       "Invalid token error",
			err:        utils.ErrInvalidToken,
			wantStatus: http.StatusUnauthorized,
			wantType:   utils.ErrInvalidToken,
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

	// Test PostgreSQL errors
	t.Run("PostgreSQL unique violation", func(t *testing.T) {
		// Create a PostgreSQL unique violation error
		pqErr := &pq.Error{
			Code:       "23505",
			Constraint: "idx_users_email",
		}

		appErr := utils.ParseError(pqErr)
		if appErr.StatusCode != http.StatusConflict {
			t.Errorf("ParseError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusConflict)
		}
		if !errors.Is(appErr.Unwrap(), utils.ErrDuplicate) {
			t.Errorf("ParseError().Unwrap() = %v, want %v", appErr.Unwrap(), utils.ErrDuplicate)
		}
	})

	t.Run("PostgreSQL foreign key violation", func(t *testing.T) {
		// Create a PostgreSQL foreign key violation error
		pqErr := &pq.Error{
			Code: "23503",
		}

		appErr := utils.ParseError(pqErr)
		if appErr.StatusCode != http.StatusBadRequest {
			t.Errorf("ParseError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusBadRequest)
		}
	})

	t.Run("PostgreSQL not null violation", func(t *testing.T) {
		// Create a PostgreSQL not null violation error
		pqErr := &pq.Error{
			Code:   "23502",
			Column: "email",
		}

		appErr := utils.ParseError(pqErr)
		if appErr.StatusCode != http.StatusBadRequest {
			t.Errorf("ParseError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusBadRequest)
		}
		if appErr.Field != "email" {
			t.Errorf("ParseError().Field = %v, want %v", appErr.Field, "email")
		}
	})

	t.Run("SQL no rows error", func(t *testing.T) {
		appErr := utils.ParseError(sql.ErrNoRows)
		if appErr.StatusCode != http.StatusNotFound {
			t.Errorf("ParseError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusNotFound)
		}
	})

	t.Run("Error with 'duplicate key' in message", func(t *testing.T) {
		err := errors.New("error: duplicate key value violates unique constraint")
		appErr := utils.ParseError(err)
		if appErr.StatusCode != http.StatusConflict {
			t.Errorf("ParseError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusConflict)
		}
	})

	t.Run("Error with 'unique constraint' in message", func(t *testing.T) {
		err := errors.New("error: violates unique constraint")
		appErr := utils.ParseError(err)
		if appErr.StatusCode != http.StatusConflict {
			t.Errorf("ParseError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusConflict)
		}
	})

	t.Run("Error with 'not found' in message", func(t *testing.T) {
		err := errors.New("record not found")
		appErr := utils.ParseError(err)
		if appErr.StatusCode != http.StatusNotFound {
			t.Errorf("ParseError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusNotFound)
		}
	})

	t.Run("Error with 'no rows' in message", func(t *testing.T) {
		err := errors.New("no rows returned")
		appErr := utils.ParseError(err)
		if appErr.StatusCode != http.StatusNotFound {
			t.Errorf("ParseError().StatusCode = %v, want %v", appErr.StatusCode, http.StatusNotFound)
		}
	})
}

func TestNewValidationErrorWithDetails(t *testing.T) {
	details := map[string]string{
		"username": "Username is required",
		"email":    "Email must be valid",
	}

	appErr := utils.NewValidationErrorWithDetails("Multiple validation errors", details)

	if appErr.Error() != "Multiple validation errors" {
		t.Errorf("NewValidationErrorWithDetails().Error() = %v, want %v", appErr.Error(), "Multiple validation errors")
	}

	if appErr.StatusCode != http.StatusBadRequest {
		t.Errorf("NewValidationErrorWithDetails().StatusCode = %v, want %v", appErr.StatusCode, http.StatusBadRequest)
	}

	if !errors.Is(appErr.Unwrap(), utils.ErrValidation) {
		t.Errorf("NewValidationErrorWithDetails().Unwrap() = %v, want %v", appErr.Unwrap(), utils.ErrValidation)
	}

	// Check that details were converted correctly
	if appErr.Details == nil {
		t.Errorf("NewValidationErrorWithDetails().Details is nil")
	} else {
		usernameMsg, ok := appErr.Details["username"]
		if !ok || usernameMsg != "Username is required" {
			t.Errorf("Details['username'] = %v, want %v", usernameMsg, "Username is required")
		}

		emailMsg, ok := appErr.Details["email"]
		if !ok || emailMsg != "Email must be valid" {
			t.Errorf("Details['email'] = %v, want %v", emailMsg, "Email must be valid")
		}
	}
}
