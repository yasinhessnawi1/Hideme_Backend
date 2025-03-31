package utils

import (
	"encoding/json"
	"net/http"

	"github.com/rs/zerolog/log"
)

// Response represents a standardized API response
type Response struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   *ErrorInfo  `json:"error,omitempty"`
	Meta    *MetaInfo   `json:"meta,omitempty"`
}

// ErrorInfo represents error information in the response
type ErrorInfo struct {
	Code    string            `json:"code"`
	Message string            `json:"message"`
	Details map[string]string `json:"details,omitempty"`
}

// MetaInfo represents metadata in the response
type MetaInfo struct {
	Page       int `json:"page,omitempty"`
	PageSize   int `json:"page_size,omitempty"`
	TotalItems int `json:"total_items,omitempty"`
	TotalPages int `json:"total_pages,omitempty"`
}

// PaginationParams contains parameters for pagination
type PaginationParams struct {
	Page     int
	PageSize int
}

// JSON sends a JSON response with the given status code and data
func JSON(w http.ResponseWriter, statusCode int, data interface{}) {
	// Create a successful response
	response := Response{
		Success: statusCode >= 200 && statusCode < 300,
		Data:    data,
	}

	SendJSON(w, statusCode, response)
}

// Error sends an error response with the given status code and error information
func Error(w http.ResponseWriter, statusCode int, code, message string, details map[string]string) {
	// Create an error response
	response := Response{
		Success: false,
		Error: &ErrorInfo{
			Code:    code,
			Message: message,
			Details: details,
		},
	}

	SendJSON(w, statusCode, response)
}

// ErrorFromAppError sends an error response based on an AppError
func ErrorFromAppError(w http.ResponseWriter, err *AppError) {
	// Extract error code from the underlying error
	errCode := "internal_error"
	switch err.Err {
	case ErrNotFound:
		errCode = "not_found"
	case ErrBadRequest:
		errCode = "bad_request"
	case ErrUnauthorized:
		errCode = "unauthorized"
	case ErrForbidden:
		errCode = "forbidden"
	case ErrValidation:
		errCode = "validation_error"
	case ErrDuplicate:
		errCode = "duplicate_resource"
	case ErrInvalidCredentials:
		errCode = "invalid_credentials"
	case ErrExpiredToken:
		errCode = "token_expired"
	case ErrInvalidToken:
		errCode = "token_invalid"
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

// Paginated sends a paginated response with the given status code, data, and pagination info
func Paginated(w http.ResponseWriter, statusCode int, data interface{}, page, pageSize, totalItems int) {
	// Calculate total pages
	totalPages := totalItems / pageSize
	if totalItems%pageSize > 0 {
		totalPages++
	}

	// Create a successful response with pagination metadata
	response := Response{
		Success: statusCode >= 200 && statusCode < 300,
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

// SendJSON is a helper function to send JSON data with proper headers
func SendJSON(w http.ResponseWriter, statusCode int, data interface{}) {
	// Set headers
	w.Header().Set("Content-Type", "application/json")
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

// NoContent sends a 204 No Content response
func NoContent(w http.ResponseWriter) {
	w.WriteHeader(http.StatusNoContent)
}

// BadRequest sends a 400 Bad Request response with the given message
func BadRequest(w http.ResponseWriter, message string, details map[string]string) {
	Error(w, http.StatusBadRequest, "bad_request", message, details)
}

// Unauthorized sends a 401 Unauthorized response with the given message
func Unauthorized(w http.ResponseWriter, message string) {
	if message == "" {
		message = "Authentication required"
	}
	Error(w, http.StatusUnauthorized, "unauthorized", message, nil)
}

// Forbidden sends a 403 Forbidden response with the given message
func Forbidden(w http.ResponseWriter, message string) {
	if message == "" {
		message = "You don't have permission to access this resource"
	}
	Error(w, http.StatusForbidden, "forbidden", message, nil)
}

// NotFound sends a 404 Not Found response with the given message
func NotFound(w http.ResponseWriter, message string) {
	if message == "" {
		message = "The requested resource could not be found"
	}
	Error(w, http.StatusNotFound, "not_found", message, nil)
}

// MethodNotAllowed sends a 405 Method Not Allowed response
func MethodNotAllowed(w http.ResponseWriter) {
	Error(w, http.StatusMethodNotAllowed, "method_not_allowed", "This method is not allowed for this resource", nil)
}

// Conflict sends a 409 Conflict response with the given message
func Conflict(w http.ResponseWriter, message string) {
	Error(w, http.StatusConflict, "conflict", message, nil)
}

// InternalServerError sends a 500 Internal Server Error response
func InternalServerError(w http.ResponseWriter, err error) {
	log.Error().Err(err).Msg("Internal server error")
	Error(w, http.StatusInternalServerError, "internal_error", "An internal server error occurred", nil)
}

// ValidationError sends a 400 Bad Request response with validation error details
func ValidationError(w http.ResponseWriter, errors map[string]string) {
	Error(w, http.StatusBadRequest, "validation_error", "Validation failed", errors)
}

// GetPaginationParams extracts pagination parameters from the request
func GetPaginationParams(r *http.Request) PaginationParams {
	// Get page and page_size parameters, with defaults
	page := 1
	pageSize := 20

	// Parse page parameter
	if r.URL.Query().Get("page") != "" {
		parsedPage, _ := parseInt(r.URL.Query().Get("page"), 1)
		page = parsedPage
	}

	// Parse page_size parameter
	if r.URL.Query().Get("page_size") != "" {
		parsedPageSize, _ := parseInt(r.URL.Query().Get("page_size"), 20)
		// Limit page size to a reasonable range
		if parsedPageSize < 1 {
			pageSize = 1
		} else if parsedPageSize > 100 {
			pageSize = 100
		} else {
			pageSize = parsedPageSize
		}
	}

	return PaginationParams{
		Page:     page,
		PageSize: pageSize,
	}
}

// Helper function to parse integers with a default value
func parseInt(s string, defaultValue int) (int, error) {
	var value int
	err := json.Unmarshal([]byte(s), &value)
	if err != nil {
		return defaultValue, err
	}
	return value, nil
}
