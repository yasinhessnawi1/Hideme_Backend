package server_test

/*
import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/server"
)

// MockDB is a mock implementation of the database.Pool interface
type MockDB struct {
	HealthCheckFunc func(ctx context.Context) error
}

func (m *MockDB) HealthCheck(ctx context.Context) error {
	if m.HealthCheckFunc != nil {
		return m.HealthCheckFunc(ctx)
	}
	return nil
}

// Additional methods needed to satisfy the database.Pool interface
func (m *MockDB) ExecContext(ctx context.Context, query string, args ...interface{}) (sql.Result, error) {
	return nil, nil
}

func (m *MockDB) QueryContext(ctx context.Context, query string, args ...interface{}) (*sql.Rows, error) {
	return nil, nil
}

func (m *MockDB) QueryRowContext(ctx context.Context, query string, args ...interface{}) *sql.Row {
	return nil
}

func (m *MockDB) Begin() (*sql.Tx, error) {
	return nil, nil
}

func (m *MockDB) BeginTx(ctx context.Context, opts *sql.TxOptions) (*sql.Tx, error) {
	return nil, nil
}

func (m *MockDB) Close() error {
	return nil
}

func (m *MockDB) Transaction(ctx context.Context, fn func(tx *sql.Tx) error) error {
	return nil
}

func TestRoutes(t *testing.T) {
	// Create a mock config
	cfg := &config.AppConfig{
		App: config.AppSettings{
			Environment: "testing",
			Name:        "HideMe_Test",
			Version:     "test-version",
		},
		CORS: config.CORSSettings{
			AllowedOrigins:   []string{"*"},
			AllowCredentials: true,
		},
	}

	// Tests for specific routes
	tests := []struct {
		name           string
		method         string
		path           string
		setupServer    func(*server.Server)
		expectedStatus int
		expectedBody   map[string]interface{}
	}{
		{
			name:   "Health check - healthy",
			method: "GET",
			path:   "/health",
			setupServer: func(s *server.Server) {
				s.Db = &MockDB{
					HealthCheckFunc: func(ctx context.Context) error {
						return nil
					},
				}
			},
			expectedStatus: http.StatusOK,
			expectedBody: map[string]interface{}{
				"status":  "healthy",
				"version": "test-version",
			},
		},
		{
			name:   "Health check - unhealthy",
			method: "GET",
			path:   "/health",
			setupServer: func(s *server.Server) {
				s.Db = &MockDB{
					HealthCheckFunc: func(ctx context.Context) error {
						return errors.New("database connection failed")
					},
				}
			},
			expectedStatus: http.StatusServiceUnavailable,
			expectedBody: map[string]interface{}{
				"success": false,
				"error": map[string]interface{}{
					"code":    "service_unavailable",
					"message": "Service is not healthy",
				},
			},
		},
		{
			name:   "Version info",
			method: "GET",
			path:   "/version",
			setupServer: func(s *server.Server) {
				// No setup needed
			},
			expectedStatus: http.StatusOK,
			expectedBody: map[string]interface{}{
				"version":     "test-version",
				"environment": "testing",
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create a basic server with minimal setup
			srv := &server.Server{
				Config: cfg,
			}

			// Run any additional setup
			if tt.setupServer != nil {
				tt.setupServer(srv)
			}

			// Setup routes
			srv.SetupRoutes()

			// Create a test request
			req, err := http.NewRequest(tt.method, tt.path, nil)
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}

			// Create a response recorder
			rr := httptest.NewRecorder()

			// Call the handler
			srv.GetRouter().ServeHTTP(rr, req)

			// Check status code
			if status := rr.Code; status != tt.expectedStatus {
				t.Errorf("Handler returned wrong status code: got %v want %v", status, tt.expectedStatus)
			}

			// Check response body if expected
			if tt.expectedBody != nil {
				var response map[string]interface{}
				if err := json.Unmarshal(rr.Body.Bytes(), &response); err != nil {
					t.Errorf("Failed to parse response body: %v", err)
					return
				}

				// Verify each expected key exists and has the correct value
				for key, expectedValue := range tt.expectedBody {
					actualValue, exists := getNestedValue(response, key)
					if !exists {
						t.Errorf("Response missing expected key %q", key)
						continue
					}

					// Check if the expected value is a map
					if expectedMap, ok := expectedValue.(map[string]interface{}); ok {
						actualMap, ok := actualValue.(map[string]interface{})
						if !ok {
							t.Errorf("Expected %q to be a map, got %T", key, actualValue)
							continue
						}

						// Verify each key in the expected map
						for subKey, expectedSubValue := range expectedMap {
							actualSubValue, exists := actualMap[subKey]
							if !exists {
								t.Errorf("Response missing expected nested key %q.%q", key, subKey)
								continue
							}
							if !reflect.DeepEqual(actualSubValue, expectedSubValue) {
								t.Errorf("Response %q.%q = %v, want %v", key, subKey, actualSubValue, expectedSubValue)
							}
						}
					} else {
						// Simple value comparison
						if !reflect.DeepEqual(actualValue, expectedValue) {
							t.Errorf("Response %q = %v, want %v", key, actualValue, expectedValue)
						}
					}
				}
			}
		})
	}
}

// Helper function to get nested values from a map
func getNestedValue(m map[string]interface{}, key string) (interface{}, bool) {
	parts := strings.Split(key, ".")
	current := m

	for i, part := range parts {
		if i == len(parts)-1 {
			// Last part
			value, exists := current[part]
			return value, exists
		}

		// Not the last part, must be another map
		nextMap, ok := current[part].(map[string]interface{})
		if !ok {
			return nil, false
		}
		current = nextMap
	}

	return nil, false // This shouldn't happen given the logic above
}

// TestRoutesExist verifies that all expected routes exist in the router
func TestRoutesExist(t *testing.T) {
	// Create a minimal config
	cfg := &config.AppConfig{
		App: config.AppSettings{
			Environment: "testing",
			Name:        "HideMe_Test",
			Version:     "test-version",
		},
		CORS: config.CORSSettings{
			AllowedOrigins:   []string{"*"},
			AllowCredentials: true,
		},
		JWT: config.JWTSettings{
			Secret: "test-secret",
			Expiry: 15 * time.Minute,
		},
	}

	// Create a server
	srv := &server.Server{
		Config: cfg,
	}

	// Setup routes
	srv.SetupRoutes()

	// Expected routes to exist (representative sample)
	expectedRoutes := []struct {
		method string
		path   string
	}{
	//	{"GET", "/health"},
	//	{"GET", "/version"},
		{"POST", "/api/auth/signup"},
		{"POST", "/api/auth/login"},
		{"POST", "/api/auth/refresh"},
		{"POST", "/api/auth/logout"},
		{"POST", "/api/auth/validate-key"},
		{"GET", "/api/auth/verify"},
		{"POST", "/api/auth/logout-all"},
		{"GET", "/api/users/check/username"},
		{"GET", "/api/users/check/email"},
		{"GET", "/api/users/me"},
		{"PUT", "/api/users/me"},
		{"DELETE", "/api/users/me"},
		{"POST", "/api/users/me/change-password"},
		{"GET", "/api/users/me/sessions"},
		{"DELETE", "/api/users/me/sessions"},
		{"GET", "/api/keys"},
		{"POST", "/api/keys"},
		{"DELETE", "/api/keys/{keyID}"},
		{"GET", "/api/settings"},
		{"PUT", "/api/settings"},
		{"GET", "/api/settings/ban-list"},
		{"POST", "/api/settings/ban-list/words"},
		{"DELETE", "/api/settings/ban-list/words"},
		{"GET", "/api/settings/patterns"},
		{"POST", "/api/settings/patterns"},
		{"PUT", "/api/settings/patterns/{patternID}"},
		{"DELETE", "/api/settings/patterns/{patternID}"},
		{"GET", "/api/settings/entities/{methodID}"},
		{"POST", "/api/settings/entities"},
		{"DELETE", "/api/settings/entities/{entityID}"},
		{"GET", "/api/db/{table}"},
		{"POST", "/api/db/{table}"},
		{"GET", "/api/db/{table}/{id}"},
		{"PUT", "/api/db/{table}/{id}"},
		{"DELETE", "/api/db/{table}/{id}"},
		{"GET", "/api/db/{table}/schema"},
	}

	// Get all registered routes
	router := srv.GetRouter()

	// For each expected route, try to make a request and check if a route handler is found
	for _, route := range expectedRoutes {
		t.Run(fmt.Sprintf("%s %s", route.method, route.path), func(t *testing.T) {
			// Create a test request with a placeholder URL
			// (Chi router won't match the exact URL with parameters, but will respond with 404 or other status)
			path := strings.Replace(strings.Replace(route.path, "{keyID}", "test-key", -1),
				"{patternID}", "1", -1)
			path = strings.Replace(strings.Replace(path, "{methodID}", "1", -1),
				"{entityID}", "1", -1)
			path = strings.Replace(strings.Replace(path, "{table}", "test_table", -1),
				"{id}", "1", -1)

			req, err := http.NewRequest(route.method, path, nil)
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}

			// Create a response recorder
			rr := httptest.NewRecorder()

			// Serve the request
			router.ServeHTTP(rr, req)

			// Check if the route is registered (should not return 404 Method Not Allowed)
			// This is a simplistic check, as protected routes will return 401 without token
			if rr.Code == http.StatusMethodNotAllowed {
				t.Errorf("Route %s %s not found (returned Method Not Allowed)", route.method, route.path)
			}
		})
	}
}


*/
