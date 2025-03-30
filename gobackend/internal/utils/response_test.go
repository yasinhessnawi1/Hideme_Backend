package utils_test

import (
	"encoding/json"
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
			// Create a response recorder
			rr := httptest.NewRecorder()

			// Call the function being tested
			utils.JSON(rr, tt.statusCode, tt.data)

			// Check status code
			if status := rr.Code; status != tt.wantStatus {
				t.Errorf("handler returned wrong status code: got %v want %v", status, tt.wantStatus)
			}

			// Check content type
			if ctype := rr.Header().Get("Content-Type"); ctype != "application/json" {
				t.Errorf("handler returned wrong content type: got %v want application/json", ctype)
			}

			// Parse the response body
			var response map[string]interface{}
			if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
				t.Fatalf("Could not parse response body: %v", err)
			}

			// Check the body content
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
			// Create a response recorder
			rr := httptest.NewRecorder()

			// Call the function being tested
			utils.Error(rr, tt.statusCode, tt.code, tt.message, tt.details)

			// Check status code
			if status := rr.Code; status != tt.wantStatus {
				t.Errorf("handler returned wrong status code: got %v want %v", status, tt.wantStatus)
			}

			// Check content type
			if ctype := rr.Header().Get("Content-Type"); ctype != "application/json" {
				t.Errorf("handler returned wrong content type: got %v want application/json", ctype)
			}

			// Parse the response body
			var response map[string]interface{}
			if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
				t.Fatalf("Could not parse response body: %v", err)
			}

			// Check the body content
			if !reflect.DeepEqual(response, tt.wantBody) {
				t.Errorf("handler returned unexpected body: got %v want %v", response, tt.wantBody)
			}
		})
	}
}

func TestPaginated(t *testing.T) {
	data := []string{"item1", "item2", "item3"}

	// Create a response recorder
	rr := httptest.NewRecorder()

	// Call the function being tested
	utils.Paginated(rr, http.StatusOK, data, 2, 10, 25)

	// Check status code
	if status := rr.Code; status != http.StatusOK {
		t.Errorf("handler returned wrong status code: got %v want %v", status, http.StatusOK)
	}

	// Parse the response body
	var response map[string]interface{}
	if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
		t.Fatalf("Could not parse response body: %v", err)
	}

	// Check success flag
	success, ok := response["success"].(bool)
	if !ok || !success {
		t.Errorf("Success flag: got %v want true", success)
	}

	// Check data
	responseData, ok := response["data"].([]interface{})
	if !ok || len(responseData) != len(data) {
		t.Errorf("Data: got %v want %v", responseData, data)
	}

	// Check metadata
	meta, ok := response["meta"].(map[string]interface{})
	if !ok {
		t.Fatalf("Response does not contain meta object")
	}

	expectedMeta := map[string]interface{}{
		"page":        float64(2),
		"page_size":   float64(10),
		"total_items": float64(25),
		"total_pages": float64(3), // 25 items with page size 10 = 3 pages
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
			wantPage:    1, // Default
			wantSize:    20,
		},
		{
			name:        "Page size too large",
			queryParams: map[string]string{"page_size": "200"},
			wantPage:    1,
			wantSize:    100, // Maximum
		},
		{
			name:        "Page size too small",
			queryParams: map[string]string{"page_size": "0"},
			wantPage:    1,
			wantSize:    1, // Minimum
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create request with query parameters
			req := httptest.NewRequest("GET", "/", nil)
			q := req.URL.Query()
			for key, value := range tt.queryParams {
				q.Add(key, value)
			}
			req.URL.RawQuery = q.Encode()

			// Get pagination parameters
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
