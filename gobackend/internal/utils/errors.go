// Package utils provides utility functions and helpers for the application.
// This file defines a robust error handling system that creates context-rich
// error objects which can be used throughout the application to provide
// consistent error handling, logging, and HTTP response generation.
//
// The error system includes:
//   - Custom error types with specific semantic meanings
//   - The AppError type which provides HTTP status codes, user messages and developer info
//   - Helper functions to create different types of errors
//   - Utility functions to check error types and extract status codes
//
// This approach centralizes error handling logic and ensures consistent
// error responses across the API.
package utils

import (
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/lib/pq"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// Custom error types for the application.
// These errors define the semantic meaning of errors that can occur
// throughout the application and can be checked with errors.Is().
var (
	// ErrNotFound indicates a requested resource could not be found
	ErrNotFound = errors.New(constants.ErrorNotFound)

	// ErrUnauthorized indicates authentication is required but was not provided or was invalid
	ErrUnauthorized = errors.New(constants.ErrorUnauthorized)

	// ErrForbidden indicates the requester does not have permission to access the resource
	ErrForbidden = errors.New(constants.ErrorForbidden)

	// ErrBadRequest indicates an invalid request was received
	ErrBadRequest = errors.New(constants.ErrorBadRequest)

	// ErrInternalServer indicates an unexpected error occurred on the server
	ErrInternalServer = errors.New(constants.ErrorInternalServer)

	// ErrValidation indicates a validation error on request data
	ErrValidation = errors.New(constants.ErrorValidation)

	// ErrDuplicate indicates an attempt to create a resource that already exists
	ErrDuplicate = errors.New(constants.ErrorDuplicate)

	// ErrInvalidCredentials indicates authentication failed due to invalid credentials
	ErrInvalidCredentials = errors.New(constants.ErrorInvalidCredentials)

	// ErrExpiredToken indicates a token has expired
	ErrExpiredToken = errors.New(constants.ErrorExpiredToken)

	// ErrInvalidToken indicates a token is invalid
	ErrInvalidToken = errors.New(constants.ErrorInvalidToken)
)

// AppError represents an application error with additional context.
// It wraps an underlying error with HTTP-specific context like status codes
// and user-friendly messages, making it easier to translate errors to HTTP responses.
type AppError struct {
	Err        error          // The underlying error
	StatusCode int            // HTTP status code
	Message    string         // User-friendly error message
	DevInfo    string         // Additional information for developers
	Field      string         // Field related to the error (for validation errors)
	Details    map[string]any // Additional structured details about the error
}

// Error implements the error interface.
// It returns a user-friendly error message, optionally prefixed with the field name.
//
// Returns:
//   - A string representation of the error suitable for display to users
func (e *AppError) Error() string {
	if e.Field != "" {
		return fmt.Sprintf("%s: %s", e.Field, e.Message)
	}
	return e.Message
}

// Unwrap returns the underlying error.
// This allows errors.Is and errors.As to work with wrapped errors.
//
// Returns:
//   - The original error that was wrapped in this AppError
func (e *AppError) Unwrap() error {
	return e.Err
}

// New creates a new AppError with the given error and status code.
//
// Parameters:
//   - err: The underlying error
//   - statusCode: The HTTP status code
//   - message: A user-friendly error message
//
// Returns:
//   - A new AppError instance
func New(err error, statusCode int, message string) *AppError {
	return &AppError{
		Err:        err,
		StatusCode: statusCode,
		Message:    message,
	}
}

// NewWithDevInfo creates a new AppError with developer information.
// This is similar to New but includes additional context for debugging.
//
// Parameters:
//   - err: The underlying error
//   - statusCode: The HTTP status code
//   - message: A user-friendly error message
//   - devInfo: Additional information for developers (not exposed to users)
//
// Returns:
//   - A new AppError instance with developer context
func NewWithDevInfo(err error, statusCode int, message, devInfo string) *AppError {
	return &AppError{
		Err:        err,
		StatusCode: statusCode,
		Message:    message,
		DevInfo:    devInfo,
	}
}

// NewValidationError creates a new validation error for a specific field.
//
// Parameters:
//   - field: The name of the field that failed validation
//   - message: A user-friendly error message
//
// Returns:
//   - A new AppError instance with validation context
func NewValidationError(field, message string) *AppError {
	return &AppError{
		Err:        ErrValidation,
		StatusCode: http.StatusBadRequest,
		Message:    message,
		Field:      field,
	}
}

// NewBadRequestError creates a new bad request error.
//
// Parameters:
//   - message: A user-friendly error message
//
// Returns:
//   - A new AppError instance for a bad request
func NewBadRequestError(message string) *AppError {
	return &AppError{
		Err:        ErrBadRequest,
		StatusCode: http.StatusBadRequest,
		Message:    message,
	}
}

// NewNotFoundError creates a new not found error.
//
// Parameters:
//   - resourceType: The type of resource that was not found (e.g., "User", "Post")
//   - identifier: The identifier that was used to look up the resource
//
// Returns:
//   - A new AppError instance for a not found error
func NewNotFoundError(resourceType string, identifier interface{}) *AppError {
	return &AppError{
		Err:        ErrNotFound,
		StatusCode: http.StatusNotFound,
		Message:    fmt.Sprintf("%s with identifier '%v' not found", resourceType, identifier),
	}
}

// NewUnauthorizedError creates a new unauthorized error.
//
// Parameters:
//   - message: A user-friendly error message (falls back to a default message if empty)
//
// Returns:
//   - A new AppError instance for an unauthorized error
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

// NewForbiddenError creates a new forbidden error.
//
// Parameters:
//   - message: A user-friendly error message (falls back to a default message if empty)
//
// Returns:
//   - A new AppError instance for a forbidden error
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

// NewInternalServerError creates a new internal server error.
// It automatically extracts the error message for developer context
// but provides a generic message to users.
//
// Parameters:
//   - err: The underlying error that occurred
//
// Returns:
//   - A new AppError instance for an internal server error
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

// NewDuplicateError creates a new duplicate resource error.
//
// Parameters:
//   - resourceType: The type of resource that has a duplicate (e.g., "User", "Email")
//   - field: The field that has a duplicate value
//   - value: The duplicate value
//
// Returns:
//   - A new AppError instance for a duplicate resource error
func NewDuplicateError(resourceType, field string, value interface{}) *AppError {
	return &AppError{
		Err:        ErrDuplicate,
		StatusCode: http.StatusConflict,
		Message:    fmt.Sprintf("%s with %s '%v' already exists", resourceType, field, value),
		Field:      field,
	}
}

// NewInvalidCredentialsError creates a new invalid credentials error.
//
// Returns:
//   - A new AppError instance for an invalid credentials error
func NewInvalidCredentialsError() *AppError {
	return &AppError{
		Err:        ErrInvalidCredentials,
		StatusCode: http.StatusUnauthorized,
		Message:    constants.MsgInvalidPassword,
	}
}

// NewExpiredTokenError creates a new expired token error.
//
// Returns:
//   - A new AppError instance for an expired token error
func NewExpiredTokenError() *AppError {
	return &AppError{
		Err:        ErrExpiredToken,
		StatusCode: http.StatusUnauthorized,
		Message:    constants.MsgTokenExpired,
	}
}

// NewInvalidTokenError creates a new invalid token error.
//
// Returns:
//   - A new AppError instance for an invalid token error
func NewInvalidTokenError() *AppError {
	return &AppError{
		Err:        ErrInvalidToken,
		StatusCode: http.StatusUnauthorized,
		Message:    constants.MsgInvalidToken,
	}
}

// ParseError attempts to parse various types of errors into an AppError.
// This function provides a centralized way to convert different error types
// (standard errors, PostgreSQL errors, etc.) into the application's error format.
//
// Parameters:
//   - err: The error to parse
//
// Returns:
//   - An AppError representing the provided error
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

// IsNotFoundError checks if an error is a not found error.
//
// Parameters:
//   - err: The error to check
//
// Returns:
//   - true if the error is a not found error, false otherwise
func IsNotFoundError(err error) bool {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.StatusCode == http.StatusNotFound
	}
	return errors.Is(err, ErrNotFound)
}

// IsDuplicateError checks if an error is a duplicate resource error.
//
// Parameters:
//   - err: The error to check
//
// Returns:
//   - true if the error is a duplicate resource error, false otherwise
func IsDuplicateError(err error) bool {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return appErr.StatusCode == http.StatusConflict
	}
	return errors.Is(err, ErrDuplicate)
}

// IsValidationError checks if an error is a validation error.
//
// Parameters:
//   - err: The error to check
//
// Returns:
//   - true if the error is a validation error, false otherwise
func IsValidationError(err error) bool {
	var appErr *AppError
	if errors.As(err, &appErr) {
		return errors.Is(appErr.Err, ErrValidation)
	}
	return errors.Is(err, ErrValidation)
}

// StatusCode returns the HTTP status code for an error.
//
// Parameters:
//   - err: The error to get the status code for
//
// Returns:
//   - The HTTP status code associated with the error, or 500 if not an AppError
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
