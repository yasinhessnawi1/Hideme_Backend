package utils_test

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

func TestJSON(t *testing.T) {
	tests := []struct {
		name       string
		statusCode int
		data       interface{}
		wantStatus int
		wantBody   map[string]interface{}
	}{
		{
			name:       "Success response",
			statusCode: http.StatusOK,
			data:       map[string]string{"message": "Success"},
			wantStatus: http.StatusOK,
			wantBody: map[string]interface{}{
				"success": true,
				"data":    map[string]interface{}{"message": "Success"},
			},
		},
		{
			name:       "Error status but with data",
			statusCode: http.StatusBadRequest,
			data:       map[string]string{"reason": "Bad input"},
			wantStatus: http.StatusBadRequest,
			wantBody: map[string]interface{}{
				"success": false,
				"data":    map[string]interface{}{"reason": "Bad input"},
			},
		},
		{
			name:       "Nil data",
			statusCode: http.StatusOK,
			data:       nil,
			wantStatus: http.StatusOK,
			wantBody: map[string]interface{}{
				"success": true,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rr := httptest.NewRecorder()
			utils.JSON(rr, tt.statusCode, tt.data)

			if status := rr.Code; status != tt.wantStatus {
				t.Errorf("handler returned wrong status code: got %v want %v", status, tt.wantStatus)
			}

			if ctype := rr.Header().Get("Content-Type"); ctype != "application/json" {
				t.Errorf("handler returned wrong content type: got %v want application/json", ctype)
			}

			var response map[string]interface{}
			if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
				t.Fatalf("Could not parse response body: %v", err)
			}

			if !reflect.DeepEqual(response, tt.wantBody) {
				t.Errorf("handler returned unexpected body: got %v want %v", response, tt.wantBody)
			}
		})
	}
}

func TestError(t *testing.T) {
	tests := []struct {
		name       string
		statusCode int
		code       string
		message    string
		details    map[string]string
		wantStatus int
		wantBody   map[string]interface{}
	}{
		{
			name:       "Basic error",
			statusCode: http.StatusBadRequest,
			code:       "invalid_input",
			message:    "Invalid input",
			details:    nil,
			wantStatus: http.StatusBadRequest,
			wantBody: map[string]interface{}{
				"success": false,
				"error": map[string]interface{}{
					"code":    "invalid_input",
					"message": "Invalid input",
				},
			},
		},
		{
			name:       "Error with details",
			statusCode: http.StatusBadRequest,
			code:       "validation_error",
			message:    "Validation failed",
			details:    map[string]string{"email": "Invalid email format"},
			wantStatus: http.StatusBadRequest,
			wantBody: map[string]interface{}{
				"success": false,
				"error": map[string]interface{}{
					"code":    "validation_error",
					"message": "Validation failed",
					"details": map[string]interface{}{
						"email": "Invalid email format",
					},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rr := httptest.NewRecorder()
			utils.Error(rr, tt.statusCode, tt.code, tt.message, tt.details)

			if status := rr.Code; status != tt.wantStatus {
				t.Errorf("handler returned wrong status code: got %v want %v", status, tt.wantStatus)
			}

			if ctype := rr.Header().Get("Content-Type"); ctype != "application/json" {
				t.Errorf("handler returned wrong content type: got %v want application/json", ctype)
			}

			var response map[string]interface{}
			if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
				t.Fatalf("Could not parse response body: %v", err)
			}

			if !reflect.DeepEqual(response, tt.wantBody) {
				t.Errorf("handler returned unexpected body: got %v want %v", response, tt.wantBody)
			}
		})
	}
}

func TestErrorFromAppError(t *testing.T) {
	tests := []struct {
		name     string
		appError *utils.AppError
		wantCode string
	}{
		{
			name: "NotFound error",
			appError: &utils.AppError{
				Err:        utils.ErrNotFound,
				StatusCode: http.StatusNotFound,
				Message:    "Resource not found",
			},
			wantCode: "not_found",
		},
		{
			name: "BadRequest error",
			appError: &utils.AppError{
				Err:        utils.ErrBadRequest,
				StatusCode: http.StatusBadRequest,
				Message:    "Invalid input",
			},
			wantCode: "bad_request",
		},
		{
			name: "Unauthorized error",
			appError: &utils.AppError{
				Err:        utils.ErrUnauthorized,
				StatusCode: http.StatusUnauthorized,
				Message:    "Not authorized",
			},
			wantCode: "unauthorized",
		},
		{
			name: "Forbidden error",
			appError: &utils.AppError{
				Err:        utils.ErrForbidden,
				StatusCode: http.StatusForbidden,
				Message:    "Access denied",
			},
			wantCode: "forbidden",
		},
		{
			name: "Validation error",
			appError: &utils.AppError{
				Err:        utils.ErrValidation,
				StatusCode: http.StatusBadRequest,
				Message:    "Validation failed",
				Field:      "email",
			},
			wantCode: "validation_error",
		},
		{
			name: "Duplicate error",
			appError: &utils.AppError{
				Err:        utils.ErrDuplicate,
				StatusCode: http.StatusConflict,
				Message:    "Resource already exists",
			},
			wantCode: "duplicate_resource",
		},
		{
			name: "InvalidCredentials error",
			appError: &utils.AppError{
				Err:        utils.ErrInvalidCredentials,
				StatusCode: http.StatusUnauthorized,
				Message:    "Invalid credentials",
			},
			wantCode: "invalid_credentials",
		},
		{
			name: "ExpiredToken error",
			appError: &utils.AppError{
				Err:        utils.ErrExpiredToken,
				StatusCode: http.StatusUnauthorized,
				Message:    "Token expired",
			},
			wantCode: "token_expired",
		},
		{
			name: "InvalidToken error",
			appError: &utils.AppError{
				Err:        utils.ErrInvalidToken,
				StatusCode: http.StatusUnauthorized,
				Message:    "Invalid token",
			},
			wantCode: "token_invalid",
		},
		{
			name: "Default error",
			appError: &utils.AppError{
				Err:        errors.New("some error"),
				StatusCode: http.StatusInternalServerError,
				Message:    "Internal error",
			},
			wantCode: "internal_error",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rr := httptest.NewRecorder()
			utils.ErrorFromAppError(rr, tt.appError)

			var response map[string]interface{}
			if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
				t.Fatalf("Could not parse response body: %v", err)
			}

			if !response["success"].(bool) != true {
				t.Error("Expected success to be false")
			}

			errorInfo := response["error"].(map[string]interface{})
			if errorInfo["code"] != tt.wantCode {
				t.Errorf("Expected error code %s, got %s", tt.wantCode, errorInfo["code"])
			}

			if errorInfo["message"] != tt.appError.Message {
				t.Errorf("Expected error message %s, got %s", tt.appError.Message, errorInfo["message"])
			}

			if tt.appError.Field != "" {
				details := errorInfo["details"].(map[string]interface{})
				if _, ok := details[tt.appError.Field]; !ok {
					t.Errorf("Expected field %s in error details", tt.appError.Field)
				}
			}
		})
	}
}

func TestNoContent(t *testing.T) {
	rr := httptest.NewRecorder()
	utils.NoContent(rr)

	if status := rr.Code; status != http.StatusNoContent {
		t.Errorf("handler returned wrong status code: got %v want %v", status, http.StatusNoContent)
	}

	if body := rr.Body.String(); body != "" {
		t.Errorf("expected empty body, got %v", body)
	}
}

func TestBadRequest(t *testing.T) {
	tests := []struct {
		name    string
		message string
		details map[string]string
	}{
		{
			name:    "With message",
			message: "Invalid input",
			details: nil,
		},
		{
			name:    "With details",
			message: "Validation failed",
			details: map[string]string{"field": "value"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rr := httptest.NewRecorder()
			utils.BadRequest(rr, tt.message, tt.details)

			if status := rr.Code; status != http.StatusBadRequest {
				t.Errorf("handler returned wrong status code: got %v want %v", status, http.StatusBadRequest)
			}

			var response map[string]interface{}
			if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
				t.Fatalf("Could not parse response body: %v", err)
			}

			errorInfo := response["error"].(map[string]interface{})
			if errorInfo["code"] != "bad_request" {
				t.Errorf("expected error code bad_request, got %v", errorInfo["code"])
			}

			if errorInfo["message"] != tt.message {
				t.Errorf("expected message %v, got %v", tt.message, errorInfo["message"])
			}
		})
	}
}

func TestUnauthorized(t *testing.T) {
	tests := []struct {
		name        string
		message     string
		wantMessage string
	}{
		{
			name:        "With custom message",
			message:     "Please log in",
			wantMessage: "Please log in",
		},
		{
			name:        "With empty message",
			message:     "",
			wantMessage: "Authentication required",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rr := httptest.NewRecorder()
			utils.Unauthorized(rr, tt.message)

			if status := rr.Code; status != http.StatusUnauthorized {
				t.Errorf("handler returned wrong status code: got %v want %v", status, http.StatusUnauthorized)
			}

			var response map[string]interface{}
			if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
				t.Fatalf("Could not parse response body: %v", err)
			}

			errorInfo := response["error"].(map[string]interface{})
			if errorInfo["code"] != "unauthorized" {
				t.Errorf("expected error code unauthorized, got %v", errorInfo["code"])
			}

			if errorInfo["message"] != tt.wantMessage {
				t.Errorf("expected message %v, got %v", tt.wantMessage, errorInfo["message"])
			}
		})
	}
}

func TestForbidden(t *testing.T) {
	tests := []struct {
		name        string
		message     string
		wantMessage string
	}{
		{
			name:        "With custom message",
			message:     "Access denied",
			wantMessage: "Access denied",
		},
		{
			name:        "With empty message",
			message:     "",
			wantMessage: "You don't have permission to access this resource",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rr := httptest.NewRecorder()
			utils.Forbidden(rr, tt.message)

			if status := rr.Code; status != http.StatusForbidden {
				t.Errorf("handler returned wrong status code: got %v want %v", status, http.StatusForbidden)
			}

			var response map[string]interface{}
			if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
				t.Fatalf("Could not parse response body: %v", err)
			}

			errorInfo := response["error"].(map[string]interface{})
			if errorInfo["code"] != "forbidden" {
				t.Errorf("expected error code forbidden, got %v", errorInfo["code"])
			}

			if errorInfo["message"] != tt.wantMessage {
				t.Errorf("expected message %v, got %v", tt.wantMessage, errorInfo["message"])
			}
		})
	}
}

func TestNotFound(t *testing.T) {
	tests := []struct {
		name        string
		message     string
		wantMessage string
	}{
		{
			name:        "With custom message",
			message:     "User not found",
			wantMessage: "User not found",
		},
		{
			name:        "With empty message",
			message:     "",
			wantMessage: "The requested resource could not be found",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			rr := httptest.NewRecorder()
			utils.NotFound(rr, tt.message)

			if status := rr.Code; status != http.StatusNotFound {
				t.Errorf("handler returned wrong status code: got %v want %v", status, http.StatusNotFound)
			}

			var response map[string]interface{}
			if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
				t.Fatalf("Could not parse response body: %v", err)
			}

			errorInfo := response["error"].(map[string]interface{})
			if errorInfo["code"] != "not_found" {
				t.Errorf("expected error code not_found, got %v", errorInfo["code"])
			}

			if errorInfo["message"] != tt.wantMessage {
				t.Errorf("expected message %v, got %v", tt.wantMessage, errorInfo["message"])
			}
		})
	}
}

func TestMethodNotAllowed(t *testing.T) {
	rr := httptest.NewRecorder()
	utils.MethodNotAllowed(rr)

	if status := rr.Code; status != http.StatusMethodNotAllowed {
		t.Errorf("handler returned wrong status code: got %v want %v", status, http.StatusMethodNotAllowed)
	}

	var response map[string]interface{}
	if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
		t.Fatalf("Could not parse response body: %v", err)
	}

	errorInfo := response["error"].(map[string]interface{})
	if errorInfo["code"] != "method_not_allowed" {
		t.Errorf("expected error code method_not_allowed, got %v", errorInfo["code"])
	}
}

func TestConflict(t *testing.T) {
	message := "Resource already exists"
	rr := httptest.NewRecorder()
	utils.Conflict(rr, message)

	if status := rr.Code; status != http.StatusConflict {
		t.Errorf("handler returned wrong status code: got %v want %v", status, http.StatusConflict)
	}

	var response map[string]interface{}
	if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
		t.Fatalf("Could not parse response body: %v", err)
	}

	errorInfo := response["error"].(map[string]interface{})
	if errorInfo["code"] != "conflict" {
		t.Errorf("expected error code conflict, got %v", errorInfo["code"])
	}

	if errorInfo["message"] != message {
		t.Errorf("expected message %v, got %v", message, errorInfo["message"])
	}
}

func TestInternalServerError(t *testing.T) {
	err := errors.New("something went wrong")
	rr := httptest.NewRecorder()
	utils.InternalServerError(rr, err)

	if status := rr.Code; status != http.StatusInternalServerError {
		t.Errorf("handler returned wrong status code: got %v want %v", status, http.StatusInternalServerError)
	}

	var response map[string]interface{}
	if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
		t.Fatalf("Could not parse response body: %v", err)
	}

	errorInfo := response["error"].(map[string]interface{})
	if errorInfo["code"] != "internal_error" {
		t.Errorf("expected error code internal_error, got %v", errorInfo["code"])
	}

	if errorInfo["message"] != "An internal server error occurred" {
		t.Errorf("expected generic error message, got %v", errorInfo["message"])
	}
}

func TestValidationError(t *testing.T) {
	errors := map[string]string{
		"username": "Username is required",
		"email":    "Invalid email format",
	}

	rr := httptest.NewRecorder()
	utils.ValidationError(rr, errors)

	if status := rr.Code; status != http.StatusBadRequest {
		t.Errorf("handler returned wrong status code: got %v want %v", status, http.StatusBadRequest)
	}

	var response map[string]interface{}
	if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
		t.Fatalf("Could not parse response body: %v", err)
	}

	errorInfo := response["error"].(map[string]interface{})
	if errorInfo["code"] != "validation_error" {
		t.Errorf("expected error code validation_error, got %v", errorInfo["code"])
	}

	if errorInfo["message"] != "Validation failed" {
		t.Errorf("expected message 'Validation failed', got %v", errorInfo["message"])
	}

	details := errorInfo["details"].(map[string]interface{})
	for key, expectedValue := range errors {
		if value, ok := details[key]; !ok || value != expectedValue {
			t.Errorf("expected detail %s to be %s, got %v", key, expectedValue, value)
		}
	}
}

func TestPaginated(t *testing.T) {
	data := []string{"item1", "item2", "item3"}

	rr := httptest.NewRecorder()
	utils.Paginated(rr, http.StatusOK, data, 2, 10, 25)

	if status := rr.Code; status != http.StatusOK {
		t.Errorf("handler returned wrong status code: got %v want %v", status, http.StatusOK)
	}

	var response map[string]interface{}
	if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
		t.Fatalf("Could not parse response body: %v", err)
	}

	success, ok := response["success"].(bool)
	if !ok || !success {
		t.Errorf("Success flag: got %v want true", success)
	}

	responseData, ok := response["data"].([]interface{})
	if !ok || len(responseData) != len(data) {
		t.Errorf("Data: got %v want %v", responseData, data)
	}

	meta, ok := response["meta"].(map[string]interface{})
	if !ok {
		t.Fatalf("Response does not contain meta object")
	}

	expectedMeta := map[string]interface{}{
		"page":        float64(2),
		"page_size":   float64(10),
		"total_items": float64(25),
		"total_pages": float64(3),
	}

	for key, expectedValue := range expectedMeta {
		if value, ok := meta[key]; !ok || value != expectedValue {
			t.Errorf("Meta %s: got %v want %v", key, value, expectedValue)
		}
	}
}

func TestGetPaginationParams(t *testing.T) {
	tests := []struct {
		name        string
		queryParams map[string]string
		wantPage    int
		wantSize    int
	}{
		{
			name:        "Default values",
			queryParams: map[string]string{},
			wantPage:    1,
			wantSize:    20,
		},
		{
			name:        "Custom values",
			queryParams: map[string]string{"page": "3", "page_size": "50"},
			wantPage:    3,
			wantSize:    50,
		},
		{
			name:        "Invalid page",
			queryParams: map[string]string{"page": "invalid"},
			wantPage:    1,
			wantSize:    20,
		},
		{
			name:        "Page size too large",
			queryParams: map[string]string{"page_size": "200"},
			wantPage:    1,
			wantSize:    100,
		},
		{
			name:        "Page size too small",
			queryParams: map[string]string{"page_size": "0"},
			wantPage:    1,
			wantSize:    1,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			req := httptest.NewRequest("GET", "/", nil)
			q := req.URL.Query()
			for key, value := range tt.queryParams {
				q.Add(key, value)
			}
			req.URL.RawQuery = q.Encode()

			params := utils.GetPaginationParams(req)

			if params.Page != tt.wantPage {
				t.Errorf("Page: got %v want %v", params.Page, tt.wantPage)
			}

			if params.PageSize != tt.wantSize {
				t.Errorf("PageSize: got %v want %v", params.PageSize, tt.wantSize)
			}
		})
	}
}
