package handlers

/*
import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// Mock DatabaseService implementation
type MockDatabaseService struct {
	ValidateTableAccessFunc func(table string) error
	ExecuteQueryFunc        func(ctx context.Context, query string, params []interface{}, userID int64) ([]map[string]interface{}, error)
	GetTableDataFunc        func(ctx context.Context, table string, conditions map[string]interface{}) ([]map[string]interface{}, error)
	GetRecordByIDFunc       func(ctx context.Context, table string, id interface{}) (map[string]interface{}, error)
	CountTableRecordsFunc   func(ctx context.Context, table string, conditions map[string]interface{}) (int64, error)
	GetTableSchemaFunc      func(ctx context.Context, table string) ([]map[string]interface{}, error)
}

func (m *MockDatabaseService) ValidateTableAccess(table string) error {
	if m.ValidateTableAccessFunc != nil {
		return m.ValidateTableAccessFunc(table)
	}
	return nil
}

func (m *MockDatabaseService) ExecuteQuery(ctx context.Context, query string, params []interface{}, userID int64) ([]map[string]interface{}, error) {
	if m.ExecuteQueryFunc != nil {
		return m.ExecuteQueryFunc(ctx, query, params, userID)
	}
	return []map[string]interface{}{{"result": "mock"}}, nil
}

func (m *MockDatabaseService) GetTableData(ctx context.Context, table string, conditions map[string]interface{}) ([]map[string]interface{}, error) {
	if m.GetTableDataFunc != nil {
		return m.GetTableDataFunc(ctx, table, conditions)
	}
	return []map[string]interface{}{{"id": 1, "name": "Test"}}, nil
}

func (m *MockDatabaseService) GetRecordByID(ctx context.Context, table string, id interface{}) (map[string]interface{}, error) {
	if m.GetRecordByIDFunc != nil {
		return m.GetRecordByIDFunc(ctx, table, id)
	}
	return map[string]interface{}{"id": id, "name": "Test Record"}, nil
}

func (m *MockDatabaseService) CountTableRecords(ctx context.Context, table string, conditions map[string]interface{}) (int64, error) {
	if m.CountTableRecordsFunc != nil {
		return m.CountTableRecordsFunc(ctx, table, conditions)
	}
	return 1, nil
}

func (m *MockDatabaseService) GetTableSchema(ctx context.Context, table string) ([]map[string]interface{}, error) {
	if m.GetTableSchemaFunc != nil {
		return m.GetTableSchemaFunc(ctx, table)
	}
	return []map[string]interface{}{
		{"column_name": "id", "data_type": "int", "is_nullable": "NO"},
		{"column_name": "name", "data_type": "varchar", "is_nullable": "NO"},
	}, nil
}

// Helper function to setup GenericHandler tests
func setupGenericHandlerTest() (*GenericHandler, *MockDatabaseService) {
	mockDBService := new(MockDatabaseService)
	handler := NewGenericHandler(mockDBService)
	return handler, mockDBService
}

// TestGetTableData tests the GetTableData handler
func TestGetTableData(t *testing.T) {
	testCases := []struct {
		name             string
		tableName        string
		queryParams      string
		setupRequest     func(*http.Request)
		mockSetup        func(*MockDatabaseService)
		expectedStatus   int
		validateResponse func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name:        "Successful Get Table Data",
			tableName:   "detection_methods",
			queryParams: "?method_name=Test",
			setupRequest: func(req *http.Request) {
				// Setup chi route context with table parameter
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("table", "detection_methods")
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockDatabaseService) {
				mock.ValidateTableAccessFunc = func(table string) error {
					if table != "detection_methods" {
						return utils.NewForbiddenError("Table not accessible")
					}
					return nil
				}
				mock.GetTableDataFunc = func(ctx context.Context, table string, conditions map[string]interface{}) ([]map[string]interface{}, error) {
					if v, ok := conditions["method_name"]; ok && v == "Test" {
						return []map[string]interface{}{
							{"method_id": 1, "method_name": "Test", "highlight_color": "#FF0000"},
						}, nil
					}
					return []map[string]interface{}{}, nil
				}
				mock.CountTableRecordsFunc = func(ctx context.Context, table string, conditions map[string]interface{}) (int64, error) {
					return 1, nil
				}
			},
			expectedStatus: http.StatusOK,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				data, ok := response["data"].([]interface{})
				if !ok {
					t.Fatalf("Expected data array in response")
				}

				if len(data) != 1 {
					t.Errorf("Expected 1 record, got %d", len(data))
				}

				record, ok := data[0].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected record to be an object")
				}

				if methodName, _ := record["method_name"].(string); methodName != "Test" {
					t.Errorf("Expected method_name 'Test', got %s", methodName)
				}

				// Check pagination metadata
				meta, ok := response["meta"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected meta object in response")
				}

				if totalItems, _ := meta["total_items"].(float64); totalItems != 1 {
					t.Errorf("Expected total_items 1, got %v", totalItems)
				}
			},
		},
		{
			name:        "Table Not Accessible",
			tableName:   "users", // Restricted table
			queryParams: "",
			setupRequest: func(req *http.Request) {
				// Setup chi route context with table parameter
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("table", "users")
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockDatabaseService) {
				mock.ValidateTableAccessFunc = func(table string) error {
					if table == "users" {
						return utils.NewForbiddenError("Table 'users' is not accessible through generic operations")
					}
					return nil
				}
			},
			expectedStatus: http.StatusForbidden,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				errObj, ok := response["error"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected error object in response")
				}

				if code, _ := errObj["code"].(string); code != "forbidden" {
					t.Errorf("Expected error code 'forbidden', got %s", code)
				}

				if message, _ := errObj["message"].(string); !strings.Contains(message, "is not accessible") {
					t.Errorf("Expected error message to contain 'is not accessible', got %s", message)
				}
			},
		},
		{
			name:        "Database Error",
			tableName:   "detection_methods",
			queryParams: "",
			setupRequest: func(req *http.Request) {
				// Setup chi route context with table parameter
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("table", "detection_methods")
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockDatabaseService) {
				mock.ValidateTableAccessFunc = func(table string) error {
					return nil
				}
				mock.GetTableDataFunc = func(ctx context.Context, table string, conditions map[string]interface{}) ([]map[string]interface{}, error) {
					return nil, errors.New("database error")
				}
			},
			expectedStatus: http.StatusInternalServerError,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				errObj, ok := response["error"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected error object in response")
				}

				if code, _ := errObj["code"].(string); code != "internal_error" {
					t.Errorf("Expected error code 'internal_error', got %s", code)
				}
			},
		},
		{
			name:        "Missing Table Parameter",
			tableName:   "",
			queryParams: "",
			setupRequest: func(req *http.Request) {
				// Setup empty chi route context
				chiCtx := chi.NewRouteContext()
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockDatabaseService) {
				// Service should not be called
			},
			expectedStatus: http.StatusBadRequest,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				errObj, ok := response["error"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected error object in response")
				}

				if message, _ := errObj["message"].(string); message != "Table name is required" {
					t.Errorf("Expected error message 'Table name is required', got %s", message)
				}
			},
		},
	}

	// Run test cases
	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Setup
			handler, mockDBService := setupGenericHandlerTest()
			if tc.mockSetup != nil {
				tc.mockSetup(mockDBService)
			}

			// Create request
			req, err := http.NewRequest("GET", "/api/db/"+tc.tableName+tc.queryParams, nil)
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}

			// Setup request context if needed
			if tc.setupRequest != nil {
				tc.setupRequest(req)
			}

			// Create response recorder
			rec := httptest.NewRecorder()

			// Call handler
			handler.GetTableData(rec, req)

			// Check status code
			if rec.Code != tc.expectedStatus {
				t.Errorf("Expected status code %d, got %d", tc.expectedStatus, rec.Code)
			}

			// Validate response
			if tc.validateResponse != nil {
				tc.validateResponse(t, rec)
			}
		})
	}
}

// TestGetRecordByID tests the GetRecordByID handler
func TestGetRecordByID(t *testing.T) {
	testCases := []struct {
		name             string
		tableName        string
		recordID         string
		setupRequest     func(*http.Request)
		mockSetup        func(*MockDatabaseService)
		expectedStatus   int
		validateResponse func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name:      "Successful Get Record By ID",
			tableName: "detection_methods",
			recordID:  "1",
			setupRequest: func(req *http.Request) {
				// Setup chi route context with table and id parameters
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("table", "detection_methods")
				chiCtx.URLParams.Add("id", "1")
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockDatabaseService) {
				mock.ValidateTableAccessFunc = func(table string) error {
					if table != "detection_methods" {
						return utils.NewForbiddenError("Table not accessible")
					}
					return nil
				}
				mock.GetRecordByIDFunc = func(ctx context.Context, table string, id interface{}) (map[string]interface{}, error) {
					if table == "detection_methods" && id == int64(1) {
						return map[string]interface{}{
							"method_id":       1,
							"method_name":     "Test Method",
							"highlight_color": "#FF0000",
						}, nil
					}
					return nil, utils.NewNotFoundError(table, id)
				}
			},
			expectedStatus: http.StatusOK,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				data, ok := response["data"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected data object in response")
				}

				if methodId, _ := data["method_id"].(float64); methodId != 1 {
					t.Errorf("Expected method_id 1, got %v", methodId)
				}

				if methodName, _ := data["method_name"].(string); methodName != "Test Method" {
					t.Errorf("Expected method_name 'Test Method', got %s", methodName)
				}
			},
		},
		{
			name:      "Record Not Found",
			tableName: "detection_methods",
			recordID:  "999",
			setupRequest: func(req *http.Request) {
				// Setup chi route context with table and id parameters
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("table", "detection_methods")
				chiCtx.URLParams.Add("id", "999")
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockDatabaseService) {
				mock.ValidateTableAccessFunc = func(table string) error {
					return nil
				}
				mock.GetRecordByIDFunc = func(ctx context.Context, table string, id interface{}) (map[string]interface{}, error) {
					return nil, utils.NewNotFoundError(table, id)
				}
			},
			expectedStatus: http.StatusNotFound,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				errObj, ok := response["error"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected error object in response")
				}

				if code, _ := errObj["code"].(string); code != "not_found" {
					t.Errorf("Expected error code 'not_found', got %s", code)
				}
			},
		},
		{
			name:      "Missing Table Parameter",
			tableName: "",
			recordID:  "1",
			setupRequest: func(req *http.Request) {
				// Setup chi route context with only id parameter
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("id", "1")
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockDatabaseService) {
				// Service should not be called
			},
			expectedStatus: http.StatusBadRequest,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				errObj, ok := response["error"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected error object in response")
				}

				if message, _ := errObj["message"].(string); message != "Table name is required" {
					t.Errorf("Expected error message 'Table name is required', got %s", message)
				}
			},
		},
		{
			name:      "Missing ID Parameter",
			tableName: "detection_methods",
			recordID:  "",
			setupRequest: func(req *http.Request) {
				// Setup chi route context with only table parameter
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("table", "detection_methods")
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockDatabaseService) {
				mock.ValidateTableAccessFunc = func(table string) error {
					return nil
				}
			},
			expectedStatus: http.StatusBadRequest,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				errObj, ok := response["error"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected error object in response")
				}

				if message, _ := errObj["message"].(string); message != "ID is required" {
					t.Errorf("Expected error message 'ID is required', got %s", message)
				}
			},
		},
	}

	// Run test cases
	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Setup
			handler, mockDBService := setupGenericHandlerTest()
			if tc.mockSetup != nil {
				tc.mockSetup(mockDBService)
			}

			// Create request
			req, err := http.NewRequest("GET", "/api/db/"+tc.tableName+"/"+tc.recordID, nil)
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}

			// Setup request context if needed
			if tc.setupRequest != nil {
				tc.setupRequest(req)
			}

			// Create response recorder
			rec := httptest.NewRecorder()

			// Call handler
			handler.GetRecordByID(rec, req)

			// Check status code
			if rec.Code != tc.expectedStatus {
				t.Errorf("Expected status code %d, got %d", tc.expectedStatus, rec.Code)
			}

			// Validate response
			if tc.validateResponse != nil {
				tc.validateResponse(t, rec)
			}
		})
	}
}

// TestGetTableSchema tests the GetTableSchema handler
func TestGetTableSchema(t *testing.T) {
	testCases := []struct {
		name             string
		tableName        string
		setupRequest     func(*http.Request)
		mockSetup        func(*MockDatabaseService)
		expectedStatus   int
		validateResponse func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name:      "Successfully Get Table Schema",
			tableName: "detection_methods",
			setupRequest: func(req *http.Request) {
				// Setup chi route context with table parameter
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("table", "detection_methods")
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockDatabaseService) {
				mock.ValidateTableAccessFunc = func(table string) error {
					if table != "detection_methods" {
						return utils.NewForbiddenError("Table not accessible")
					}
					return nil
				}
				mock.GetTableSchemaFunc = func(ctx context.Context, table string) ([]map[string]interface{}, error) {
					return []map[string]interface{}{
						{
							"column_name":    "method_id",
							"data_type":      "bigint",
							"is_nullable":    "NO",
							"column_default": nil,
						},
						{
							"column_name":    "method_name",
							"data_type":      "varchar",
							"is_nullable":    "NO",
							"column_default": nil,
						},
						{
							"column_name":    "highlight_color",
							"data_type":      "varchar",
							"is_nullable":    "NO",
							"column_default": nil,
						},
					}, nil
				}
			},
			expectedStatus: http.StatusOK,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				data, ok := response["data"].([]interface{})
				if !ok {
					t.Fatalf("Expected data array in response")
				}

				if len(data) != 3 {
					t.Errorf("Expected 3 columns, got %d", len(data))
				}

				// Check the first column
				firstColumn, ok := data[0].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected column to be an object")
				}

				if columnName, _ := firstColumn["column_name"].(string); columnName != "method_id" {
					t.Errorf("Expected column_name 'method_id', got %s", columnName)
				}

				if dataType, _ := firstColumn["data_type"].(string); dataType != "bigint" {
					t.Errorf("Expected data_type 'bigint', got %s", dataType)
				}
			},
		},
		{
			name:      "Table Not Accessible",
			tableName: "users", // Restricted table
			setupRequest: func(req *http.Request) {
				// Setup chi route context with table parameter
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("table", "users")
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockDatabaseService) {
				mock.ValidateTableAccessFunc = func(table string) error {
					if table == "users" {
						return utils.NewForbiddenError("Table 'users' is not accessible through generic operations")
					}
					return nil
				}
			},
			expectedStatus: http.StatusForbidden,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				errObj, ok := response["error"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected error object in response")
				}

				if code, _ := errObj["code"].(string); code != "forbidden" {
					t.Errorf("Expected error code 'forbidden', got %s", code)
				}
			},
		},
		{
			name:      "Missing Table Parameter",
			tableName: "",
			setupRequest: func(req *http.Request) {
				// Setup empty chi route context
				chiCtx := chi.NewRouteContext()
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockDatabaseService) {
				// Service should not be called
			},
			expectedStatus: http.StatusBadRequest,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				errObj, ok := response["error"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected error object in response")
				}

				if message, _ := errObj["message"].(string); message != "Table name is required" {
					t.Errorf("Expected error message 'Table name is required', got %s", message)
				}
			},
		},
		{
			name:      "Service Error",
			tableName: "detection_methods",
			setupRequest: func(req *http.Request) {
				// Setup chi route context with table parameter
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("table", "detection_methods")
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockDatabaseService) {
				mock.ValidateTableAccessFunc = func(table string) error {
					return nil
				}
				mock.GetTableSchemaFunc = func(ctx context.Context, table string) ([]map[string]interface{}, error) {
					return nil, errors.New("database error")
				}
			},
			expectedStatus: http.StatusInternalServerError,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				errObj, ok := response["error"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected error object in response")
				}

				if code, _ := errObj["code"].(string); code != "internal_error" {
					t.Errorf("Expected error code 'internal_error', got %s", code)
				}
			},
		},
	}

	// Run test cases
	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Setup
			handler, mockDBService := setupGenericHandlerTest()
			if tc.mockSetup != nil {
				tc.mockSetup(mockDBService)
			}

			// Create request
			req, err := http.NewRequest("GET", "/api/db/"+tc.tableName+"/schema", nil)
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}

			// Setup request context if needed
			if tc.setupRequest != nil {
				tc.setupRequest(req)
			}

			// Create response recorder
			rec := httptest.NewRecorder()

			// Call handler
			handler.GetTableSchema(rec, req)

			// Check status code
			if rec.Code != tc.expectedStatus {
				t.Errorf("Expected status code %d, got %d", tc.expectedStatus, rec.Code)
			}

			// Validate response
			if tc.validateResponse != nil {
				tc.validateResponse(t, rec)
			}
		})
	}
}

// Additional tests for CreateRecord, UpdateRecord, and DeleteRecord would follow a similar pattern

*/
