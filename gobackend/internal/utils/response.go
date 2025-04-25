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

// Error sends an error response with the given status code and error information
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

// ErrorFromAppError sends an error response based on an AppError
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

// Paginated sends a paginated response with the given status code, data, and pagination info
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

// SendJSON is a helper function to send JSON data with proper headers
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

// NoContent sends a 204 No Content response
func NoContent(w http.ResponseWriter) {
	w.WriteHeader(constants.StatusNoContent)
}

// BadRequest sends a 400 Bad Request response with the given message
func BadRequest(w http.ResponseWriter, message string, details map[string]string) {
	Error(w, constants.StatusBadRequest, constants.CodeBadRequest, message, details)
}

// Unauthorized sends a 401 Unauthorized response with the given message
func Unauthorized(w http.ResponseWriter, message string) {
	if message == "" {
		message = constants.MsgAuthRequired
	}
	Error(w, constants.StatusUnauthorized, constants.CodeUnauthorized, message, nil)
}

// Forbidden sends a 403 Forbidden response with the given message
func Forbidden(w http.ResponseWriter, message string) {
	if message == "" {
		message = constants.MsgAccessDenied
	}
	Error(w, constants.StatusForbidden, constants.CodeForbidden, message, nil)
}

// NotFound sends a 404 Not Found response with the given message
func NotFound(w http.ResponseWriter, message string) {
	if message == "" {
		message = constants.MsgResourceNotFound
	}
	Error(w, constants.StatusNotFound, constants.CodeNotFound, message, nil)
}

// MethodNotAllowed sends a 405 Method Not Allowed response
func MethodNotAllowed(w http.ResponseWriter) {
	Error(w, constants.StatusMethodNotAllowed, constants.CodeMethodNotAllowed, constants.MsgMethodNotAllowed, nil)
}

// Conflict sends a 409 Conflict response with the given message
func Conflict(w http.ResponseWriter, message string) {
	Error(w, constants.StatusConflict, constants.CodeConflict, message, nil)
}

// InternalServerError sends a 500 Internal Server Error response
func InternalServerError(w http.ResponseWriter, err error) {
	log.Error().Err(err).Msg("Internal server error")
	Error(w, constants.StatusInternalServerError, constants.CodeInternalError, constants.MsgInternalServerError, nil)
}

// ValidationError sends a 400 Bad Request response with validation error details
func ValidationError(w http.ResponseWriter, errors map[string]string) {
	Error(w, constants.StatusBadRequest, constants.CodeValidationError, "Validation failed", errors)
}

// GetPaginationParams extracts pagination parameters from the request
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

// Helper function to parse integers with a default value
func parseInt(s string, defaultValue int) (int, error) {
	var value int
	err := json.Unmarshal([]byte(s), &value)
	if err != nil {
		return defaultValue, err
	}
	return value, nil
}
