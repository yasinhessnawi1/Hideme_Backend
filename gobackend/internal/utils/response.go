// Package utils provides utility functions and helpers for the application.
// This file implements a standardized API response system that ensures
// consistent response formats across all API endpoints.
//
// The response system includes:
//   - A standard Response structure for all API responses
//   - Convenience functions for common response types (success, error, pagination)
//   - HTTP status code helpers
//   - Pagination parameter extraction
//
// This ensures that all API responses follow the same format, making it easier
// for clients to parse and handle responses predictably.
package utils

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// Response represents a standardized API response.
// All API endpoints return responses in this format for consistency.
type Response struct {
	Success bool        `json:"success"`         // Whether the request was successful
	Data    interface{} `json:"data,omitempty"`  // The response data (omitted for error responses)
	Error   *ErrorInfo  `json:"error,omitempty"` // Error information (omitted for successful responses)
	Meta    *MetaInfo   `json:"meta,omitempty"`  // Metadata such as pagination information
}

// ErrorInfo represents error information in the response.
// This provides structured error information to clients.
type ErrorInfo struct {
	Code    string            `json:"code"`              // A machine-readable error code
	Message string            `json:"message"`           // A human-readable error message
	Details map[string]string `json:"details,omitempty"` // Additional details about the error (e.g., validation errors)
}

// MetaInfo represents metadata in the response.
// This is primarily used for pagination information.
type MetaInfo struct {
	Page       int `json:"page,omitempty"`        // The current page number
	PageSize   int `json:"page_size,omitempty"`   // The number of items per page
	TotalItems int `json:"total_items,omitempty"` // The total number of items
	TotalPages int `json:"total_pages,omitempty"` // The total number of pages
}

// PaginationParams contains parameters for pagination.
// This struct is used to extract and validate pagination parameters from requests.
type PaginationParams struct {
	Page     int // The requested page number
	PageSize int // The requested page size
}

// JSON sends a JSON response with the given status code and data.
// This is the primary function for sending successful responses.
//
// Parameters:
//   - w: The HTTP response writer
//   - statusCode: The HTTP status code
//   - data: The data to include in the response
//
// The function automatically sets the success flag based on the status code.
func JSON(w http.ResponseWriter, statusCode int, data interface{}) {
	// Create a successful response
	response := Response{
		Success: statusCode >= 200 && statusCode < 300,
		Data:    data,
	}

	SendJSON(w, statusCode, response)
}

// JsonFile sends a JSON file as a downloadable attachment.
// This is useful for exporting data that should be saved as a file.
//
// Parameters:
//   - w: The HTTP response writer
//   - data: The data to include in the file
//   - filename: The name of the file to be downloaded
//
// The function automatically adds .json extension if missing and sets appropriate
// headers for file download.
func JsonFile(w http.ResponseWriter, data interface{}, filename string) {
	// Ensure filename ends with .json
	if !strings.HasSuffix(strings.ToLower(filename), ".json") {
		filename += ".json"
	}

	// Marshal the data to JSON with pretty-printing
	jsonData, err := json.MarshalIndent(data, "", "  ")
	if err != nil {
		log.Error().Err(err).Msg("Failed to marshal JSON file response")
		w.WriteHeader(http.StatusInternalServerError)
		if _, err := w.Write([]byte(`{"error":"Failed to generate file"}`)); err != nil {
			log.Error().Err(err).Msg("Failed to write error response")
		}
		return
	}

	// Set headers for file download
	w.Header().Set(constants.HeaderContentType, constants.ContentTypeOctetStream)
	w.Header().Set(constants.HeaderContentLength, fmt.Sprintf("%d", len(jsonData)))

	// This is the critical line - format it EXACTLY as shown:
	w.Header().Set(constants.HeaderContentDisposition,
		fmt.Sprintf("attachment; filename=\"%s\"; filename*=UTF-8''%s",
			filename,
			url.PathEscape(filename)))

	// Add cache control headers to prevent caching
	w.Header().Set(constants.HeaderCacheControl, constants.CacheControlNoStore)
	w.Header().Set(constants.HeaderPragma, constants.PragmaNoCache)
	w.Header().Set(constants.HeaderExpires, constants.ExpiresZero)

	w.WriteHeader(http.StatusOK)

	// Write the JSON data
	if _, err := w.Write(jsonData); err != nil {
		log.Error().Err(err).Msg("Failed to write JSON file response")
	}
}

// Error sends an error response with the given status code and error information.
// This is the primary function for sending error responses.
//
// Parameters:
//   - w: The HTTP response writer
//   - statusCode: The HTTP status code
//   - code: A machine-readable error code
//   - message: A human-readable error message
//   - details: Additional details about the error (e.g., validation errors)
func Error(w http.ResponseWriter, statusCode int, code, message string, details map[string]string) {
	// Create an error response
	response := Response{
		Success: constants.ResponseFailure,
		Error: &ErrorInfo{
			Code:    code,
			Message: message,
			Details: details,
		},
	}

	SendJSON(w, statusCode, response)
}

// ErrorFromAppError sends an error response based on an AppError.
// This provides a convenient way to convert application errors to API responses.
//
// Parameters:
//   - w: The HTTP response writer
//   - err: The application error
//
// The function extracts the error code, message, and details from the AppError
// and sends an appropriate error response.
func ErrorFromAppError(w http.ResponseWriter, err *AppError) {
	// Extract error code from the underlying error
	errCode := constants.CodeInternalError
	switch err.Err {
	case ErrNotFound:
		errCode = constants.CodeNotFound
	case ErrBadRequest:
		errCode = constants.CodeBadRequest
	case ErrUnauthorized:
		errCode = constants.CodeUnauthorized
	case ErrForbidden:
		errCode = constants.CodeForbidden
	case ErrValidation:
		errCode = constants.CodeValidationError
	case ErrDuplicate:
		errCode = constants.CodeDuplicateResource
	case ErrInvalidCredentials:
		errCode = constants.CodeInvalidCredentials
	case ErrExpiredToken:
		errCode = constants.CodeTokenExpired
	case ErrInvalidToken:
		errCode = constants.CodeTokenInvalid
	}

	// Create error details if field is present
	var details map[string]string
	if err.Field != "" {
		details = map[string]string{
			err.Field: err.Message,
		}
	}

	// Send the error response
	Error(w, err.StatusCode, errCode, err.Message, details)
}

// Paginated sends a paginated response with the given status code, data, and pagination info.
// This is used for endpoints that return collections of items.
//
// Parameters:
//   - w: The HTTP response writer
//   - statusCode: The HTTP status code
//   - data: The data to include in the response
//   - page: The current page number
//   - pageSize: The number of items per page
//   - totalItems: The total number of items
//
// The function automatically calculates the total number of pages based on the page size
// and total items.
func Paginated(w http.ResponseWriter, statusCode int, data interface{}, page, pageSize, totalItems int) {
	// Calculate total pages
	totalPages := totalItems / pageSize
	if totalItems%pageSize > 0 {
		totalPages++
	}

	// Create a successful response with pagination metadata
	response := Response{
		Success: constants.ResponseSuccess,
		Data:    data,
		Meta: &MetaInfo{
			Page:       page,
			PageSize:   pageSize,
			TotalItems: totalItems,
			TotalPages: totalPages,
		},
	}

	SendJSON(w, statusCode, response)
}

// SendJSON is a helper function to send JSON data with proper headers.
// This handles JSON marshaling and error handling for all response types.
//
// Parameters:
//   - w: The HTTP response writer
//   - statusCode: The HTTP status code
//   - data: The data to marshal to JSON and send
func SendJSON(w http.ResponseWriter, statusCode int, data interface{}) {
	// Set headers
	w.Header().Set(constants.HeaderContentType, constants.ContentTypeJSON)
	w.WriteHeader(statusCode)

	// Marshal the data to JSON
	jsonData, err := json.Marshal(data)
	if err != nil {
		// If marshaling fails, log the error and send a simple error response
		log.Error().Err(err).Msg("Failed to marshal JSON response")
		w.WriteHeader(http.StatusInternalServerError)
		if _, err := w.Write([]byte(`{"success":false,"error":{"code":"internal_error","message":"Failed to generate response"}}`)); err != nil {
			log.Error().Err(err).Msg("Failed to write error response")
		}
		return
	}

	// Write the JSON data to the response
	_, err = w.Write(jsonData)
	if err != nil {
		// Log write errors but don't try to recover
		log.Error().Err(err).Msg("Failed to write JSON response")
	}
}

// NoContent sends a 204 No Content response.
// This is used for successful operations that don't return any data.
//
// Parameters:
//   - w: The HTTP response writer
func NoContent(w http.ResponseWriter) {
	w.WriteHeader(constants.StatusNoContent)
}

// BadRequest sends a 400 Bad Request response with the given message.
// This is a convenience function for sending bad request errors.
//
// Parameters:
//   - w: The HTTP response writer
//   - message: A human-readable error message
//   - details: Additional details about the error
func BadRequest(w http.ResponseWriter, message string, details map[string]string) {
	Error(w, constants.StatusBadRequest, constants.CodeBadRequest, message, details)
}

// Unauthorized sends a 401 Unauthorized response with the given message.
// This is a convenience function for sending unauthorized errors.
//
// Parameters:
//   - w: The HTTP response writer
//   - message: A human-readable error message (falls back to a default message if empty)
func Unauthorized(w http.ResponseWriter, message string) {
	if message == "" {
		message = constants.MsgAuthRequired
	}
	Error(w, constants.StatusUnauthorized, constants.CodeUnauthorized, message, nil)
}

// Forbidden sends a 403 Forbidden response with the given message.
// This is a convenience function for sending forbidden errors.
//
// Parameters:
//   - w: The HTTP response writer
//   - message: A human-readable error message (falls back to a default message if empty)
func Forbidden(w http.ResponseWriter, message string) {
	if message == "" {
		message = constants.MsgAccessDenied
	}
	Error(w, constants.StatusForbidden, constants.CodeForbidden, message, nil)
}

// NotFound sends a 404 Not Found response with the given message.
// This is a convenience function for sending not found errors.
//
// Parameters:
//   - w: The HTTP response writer
//   - message: A human-readable error message (falls back to a default message if empty)
func NotFound(w http.ResponseWriter, message string) {
	if message == "" {
		message = constants.MsgResourceNotFound
	}
	Error(w, constants.StatusNotFound, constants.CodeNotFound, message, nil)
}

// MethodNotAllowed sends a 405 Method Not Allowed response.
// This is a convenience function for sending method not allowed errors.
//
// Parameters:
//   - w: The HTTP response writer
func MethodNotAllowed(w http.ResponseWriter) {
	Error(w, constants.StatusMethodNotAllowed, constants.CodeMethodNotAllowed, constants.MsgMethodNotAllowed, nil)
}

// Conflict sends a 409 Conflict response with the given message.
// This is a convenience function for sending conflict errors.
//
// Parameters:
//   - w: The HTTP response writer
//   - message: A human-readable error message
func Conflict(w http.ResponseWriter, message string) {
	Error(w, constants.StatusConflict, constants.CodeConflict, message, nil)
}

// InternalServerError sends a 500 Internal Server Error response.
// This is a convenience function for sending internal server errors.
//
// Parameters:
//   - w: The HTTP response writer
//   - err: The error that occurred (logged but not exposed to the client)
func InternalServerError(w http.ResponseWriter, err error) {
	log.Error().Err(err).Msg("Internal server error")
	Error(w, constants.StatusInternalServerError, constants.CodeInternalError, constants.MsgInternalServerError, nil)
}

// ValidationError sends a 400 Bad Request response with validation error details.
// This is a convenience function for sending validation errors.
//
// Parameters:
//   - w: The HTTP response writer
//   - errors: A map of field names to error messages
func ValidationError(w http.ResponseWriter, errors map[string]string) {
	Error(w, constants.StatusBadRequest, constants.CodeValidationError, "Validation failed", errors)
}

// GetPaginationParams extracts pagination parameters from the request.
// This provides a standardized way to handle pagination across all endpoints.
//
// Parameters:
//   - r: The HTTP request
//
// Returns:
//   - A PaginationParams struct containing the page and page size
//
// The function enforces minimum and maximum page sizes and provides sensible defaults.
func GetPaginationParams(r *http.Request) PaginationParams {
	// Get page and page_size parameters, with defaults
	page := constants.DefaultPage
	pageSize := constants.DefaultPageSize

	// Parse page parameter
	if r.URL.Query().Get(constants.QueryParamPage) != "" {
		parsedPage, _ := parseInt(r.URL.Query().Get(constants.QueryParamPage), constants.DefaultPage)
		page = parsedPage
	}

	// Parse page_size parameter
	if r.URL.Query().Get(constants.QueryParamPageSize) != "" {
		parsedPageSize, _ := parseInt(r.URL.Query().Get(constants.QueryParamPageSize), constants.DefaultPageSize)
		// Limit page size to a reasonable range
		if parsedPageSize < constants.MinPageSize {
			pageSize = constants.MinPageSize
		} else if parsedPageSize > constants.MaxPageSize {
			pageSize = constants.MaxPageSize
		} else {
			pageSize = parsedPageSize
		}
	}

	return PaginationParams{
		Page:     page,
		PageSize: pageSize,
	}
}

// parseInt is a helper function to parse integers with a default value.
// It handles invalid input gracefully by returning the default value.
//
// Parameters:
//   - s: The string to parse
//   - defaultValue: The default value to return if parsing fails
//
// Returns:
//   - The parsed integer or the default value if parsing fails
//   - Any error that occurred during parsing
func parseInt(s string, defaultValue int) (int, error) {
	var value int
	err := json.Unmarshal([]byte(s), &value)
	if err != nil {
		return defaultValue, err
	}
	return value, nil
}
