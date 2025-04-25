package utils

import (
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/lib/pq"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// Custom error types for the application
var (
	ErrNotFound           = errors.New(constants.ErrorNotFound)
	ErrUnauthorized       = errors.New(constants.ErrorUnauthorized)
	ErrForbidden          = errors.New(constants.ErrorForbidden)
	ErrBadRequest         = errors.New(constants.ErrorBadRequest)
	ErrInternalServer     = errors.New(constants.ErrorInternalServer)
	ErrValidation         = errors.New(constants.ErrorValidation)
	ErrDuplicate          = errors.New(constants.ErrorDuplicate)
	ErrInvalidCredentials = errors.New(constants.ErrorInvalidCredentials)
	ErrExpiredToken       = errors.New(constants.ErrorExpiredToken)
	ErrInvalidToken       = errors.New(constants.ErrorInvalidToken)
)

// AppError represents an application error with additional context
type AppError struct {
	Err        error  // The underlying error
	StatusCode int    // HTTP status code
	Message    string // User-friendly error message
	DevInfo    string // Additional information for developers
	Field      string // Field related to the error (for validation errors)
	Details    map[string]any
}

// Error implements the error interface
func (e *AppError) Error() string {
	if e.Field != "" {
		return fmt.Sprintf("%s: %s", e.Field, e.Message)
	}
	return e.Message
}

// Unwrap returns the underlying error
func (e *AppError) Unwrap() error {
	return e.Err
}

// New creates a new AppError with the given error and status code
func New(err error, statusCode int, message string) *AppError {
	return &AppError{
		Err:        err,
		StatusCode: statusCode,
		Message:    message,
	}
}

// NewWithDevInfo creates a new AppError with developer information
func NewWithDevInfo(err error, statusCode int, message, devInfo string) *AppError {
	return &AppError{
		Err:        err,
		StatusCode: statusCode,
		Message:    message,
		DevInfo:    devInfo,
	}
}

// NewValidationError creates a new validation error for a specific field
func NewValidationError(field, message string) *AppError {
	return &AppError{
		Err:        ErrValidation,
		StatusCode: http.StatusBadRequest,
		Message:    message,
		Field:      field,
	}
}

// NewBadRequestError creates a new bad request error
func NewBadRequestError(message string) *AppError {
	return &AppError{
		Err:        ErrBadRequest,
		StatusCode: http.StatusBadRequest,
		Message:    message,
	}
}

// NewNotFoundError creates a new not found error
func NewNotFoundError(resourceType string, identifier interface{}) *AppError {
	return &AppError{
		Err:        ErrNotFound,
		StatusCode: http.StatusNotFound,
		Message:    fmt.Sprintf("%s with identifier '%v' not found", resourceType, identifier),
	}
}

// NewUnauthorizedError creates a new unauthorized error
func NewUnauthorizedError(message string) *AppError {
	if message == "" {
		message = constants.MsgAuthRequired
	}
	return &AppError{
		Err:        ErrUnauthorized,
		StatusCode: http.StatusUnauthorized,
		Message:    message,
	}
}

// NewForbiddenError creates a new forbidden error
func NewForbiddenError(message string) *AppError {
	if message == "" {
		message = constants.MsgAccessDenied
	}
	return &AppError{
		Err:        ErrForbidden,
		StatusCode: http.StatusForbidden,
		Message:    message,
	}
}

// NewInternalServerError creates a new internal server error
func NewInternalServerError(err error) *AppError {
	devInfo := ""
	if err != nil {
		devInfo = err.Error()
	}
	return &AppError{
		Err:        ErrInternalServer,
		StatusCode: http.StatusInternalServerError,
		Message:    constants.MsgInternalServerError,
		DevInfo:    devInfo,
	}
}

// NewDuplicateError creates a new duplicate resource error
func NewDuplicateError(resourceType, field string, value interface{}) *AppError {
	return &AppError{
		Err:        ErrDuplicate,
		StatusCode: http.StatusConflict,
		Message:    fmt.Sprintf("%s with %s '%v' already exists", resourceType, field, value),
		Field:      field,
	}
}

// NewInvalidCredentialsError creates a new invalid credentials error
func NewInvalidCredentialsError() *AppError {
	return &AppError{
		Err:        ErrInvalidCredentials,
		StatusCode: http.StatusUnauthorized,
		Message:    constants.MsgInvalidPassword,
	}
}

// NewExpiredTokenError creates a new expired token error
func NewExpiredTokenError() *AppError {
	return &AppError{
		Err:        ErrExpiredToken,
		StatusCode: http.StatusUnauthorized,
		Message:    constants.MsgTokenExpired,
	}
}

// NewInvalidTokenError creates a new invalid token error
func NewInvalidTokenError() *AppError {
	return &AppError{
		Err:        ErrInvalidToken,
		StatusCode: http.StatusUnauthorized,
		Message:    constants.MsgInvalidToken,
	}
}

// ParseError attempts to parse various types of errors into an AppError
func ParseError(err error) *AppError {
	// If it's already an AppError, return it
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr
	}

	// Check for specific error types
	switch {
	case errors.Is(err, ErrNotFound):
		return NewNotFoundError("Resource", "")
	case errors.Is(err, ErrUnauthorized):
		return NewUnauthorizedError("")
	case errors.Is(err, ErrForbidden):
		return NewForbiddenError("")
	case errors.Is(err, ErrBadRequest):
		return NewBadRequestError(err.Error())
	case errors.Is(err, ErrValidation):
		return NewValidationError("", err.Error())
	case errors.Is(err, ErrDuplicate):
		return NewDuplicateError("Resource", "", "")
	case errors.Is(err, ErrInvalidCredentials):
		return NewInvalidCredentialsError()
	case errors.Is(err, ErrExpiredToken):
		return NewExpiredTokenError()
	case errors.Is(err, ErrInvalidToken):
		return NewInvalidTokenError()
	}

	// Check for PostgreSQL-specific errors
	var pqErr *pq.Error
	if errors.As(err, &pqErr) {
		// Log the database error with GDPR considerations
		logContext := map[string]interface{}{
			"error_code": pqErr.Code,
			"error_type": "database_error",
		}

		LogError(err, logContext)

		switch pqErr.Code {
		case constants.PGErrorDuplicateConstraint: // unique_violation
			// Try to extract the constraint name for more specific error messages
			constraint := pqErr.Constraint
			field := ""
			if strings.Contains(constraint, "idx_") {
				parts := strings.Split(constraint, "idx_")
				if len(parts) > 1 {
					field = parts[1]
				}
			}
			return &AppError{
				Err:        ErrDuplicate,
				StatusCode: http.StatusConflict,
				Message:    constants.MsgResourceAlreadyExists,
				DevInfo:    pqErr.Error(),
				Field:      field,
			}
		case constants.PGErrorForeignKeyConstraint: // foreign_key_violation
			return &AppError{
				Err:        ErrBadRequest,
				StatusCode: http.StatusBadRequest,
				Message:    "This operation violates a foreign key constraint",
				DevInfo:    pqErr.Error(),
			}
		case constants.PGErrorNotNullConstraint: // not_null_violation
			field := pqErr.Column
			return &AppError{
				Err:        ErrValidation,
				StatusCode: http.StatusBadRequest,
				Message:    fmt.Sprintf("The %s field cannot be empty", field),
				DevInfo:    pqErr.Error(),
				Field:      field,
			}
		}
	}

	// Check for general database-specific error patterns
	errMsg := strings.ToLower(err.Error())

	// Log general errors with minimal context to avoid logging PII
	LogError(err, map[string]interface{}{
		"error_type": "general_error",
	})

	switch {
	case strings.Contains(errMsg, constants.DBErrorDuplicateKey) || strings.Contains(errMsg, "unique constraint"):
		return &AppError{
			Err:        ErrDuplicate,
			StatusCode: http.StatusConflict,
			Message:    constants.MsgResourceAlreadyExists,
			DevInfo:    err.Error(),
		}
	case strings.Contains(errMsg, "not found") || strings.Contains(errMsg, "no rows"):
		return &AppError{
			Err:        ErrNotFound,
			StatusCode: http.StatusNotFound,
			Message:    constants.MsgResourceNotFound,
			DevInfo:    err.Error(),
		}
	}

	// Default to internal server error
	return NewInternalServerError(err)
}

// IsNotFoundError checks if an error is a not found error
func IsNotFoundError(err error) bool {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.StatusCode == http.StatusNotFound
	}
	return errors.Is(err, ErrNotFound)
}

// IsDuplicateError checks if an error is a duplicate resource error
func IsDuplicateError(err error) bool {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.StatusCode == http.StatusConflict
	}
	return errors.Is(err, ErrDuplicate)
}

// IsValidationError checks if an error is a validation error
func IsValidationError(err error) bool {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return errors.Is(appErr.Err, ErrValidation)
	}
	return errors.Is(err, ErrValidation)
}

// StatusCode returns the HTTP status code for an error
func StatusCode(err error) int {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.StatusCode
	}
	return http.StatusInternalServerError
}

/*
// IsDuplicateKeyError checks if an error is a duplicate key error (PostgreSQL specific)
func IsDuplicateKeyError(err error) bool {
	var pqErr *pq.Error
	if errors.As(err, &pqErr) {
		// 23505 is the PostgreSQL error code for unique_violation
		return pqErr.Code == "23505"
	}
	return false
}
/*
// IsUniqueViolation checks if an error is a unique violation for a specific constraint
func IsUniqueViolation(err error, constraintName string) bool {
	var pqErr *pq.Error
	if errors.As(err, &pqErr) {
		// Check for unique violation and specific constraint
		return pqErr.Code == "23505" && strings.Contains(pqErr.Constraint, constraintName)
	}
	return false
}

// IsNotNullViolation checks if an error is a not-null violation
func IsNotNullViolation(err error) bool {
	var pqErr *pq.Error
	if errors.As(err, &pqErr) {
		// PostgreSQL error code 23502 is "not_null_violation"
		return pqErr.Code == "23502"
	}
	return false
}

// IsForeignKeyViolation checks if an error is a foreign key violation
func IsForeignKeyViolation(err error) bool {
	var pqErr *pq.Error
	if errors.As(err, &pqErr) {
		// PostgreSQL error code 23503 is "foreign_key_violation"
		return pqErr.Code == "23503"
	}
	return false
}

*/
