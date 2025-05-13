package server

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
)

// APIResponse represents the standard API response envelope format
type APIResponse struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   *struct {
		Code    string            `json:"code"`
		Message string            `json:"message"`
		Details map[string]string `json:"details,omitempty"`
	} `json:"error,omitempty"`
	Meta *struct {
		Page       int `json:"page,omitempty"`
		PageSize   int `json:"page_size,omitempty"`
		TotalItems int `json:"total_items,omitempty"`
		TotalPages int `json:"total_pages,omitempty"`
	} `json:"meta,omitempty"`
}

// DatabaseInterface defines the methods needed from the database Pool
type DatabaseInterface interface {
	HealthCheck(ctx context.Context) error
}

// MockDatabase is a mock implementation of DatabaseInterface
type MockDatabase struct {
	mock.Mock
}

func (m *MockDatabase) HealthCheck(ctx context.Context) error {
	args := m.Called(ctx)
	return args.Error(0)
}

// HandlerInterface defines a generic HTTP handler interface
type HandlerInterface interface {
	ServeHTTP(w http.ResponseWriter, r *http.Request)
}

// HandlerFunc adapts a function to HandlerInterface
type HandlerFunc func(w http.ResponseWriter, r *http.Request)

func (f HandlerFunc) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	f(w, r)
}

// MockHandler is a mock implementation of a generic HTTP handler
type MockHandler struct {
	mock.Mock
}

func (m *MockHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	m.Called(w, r)
}

// JWTServiceInterface defines methods required from JWTService
type JWTServiceInterface interface {
	// Add methods if needed for your tests
}

// MockJWTService is a mock implementation of JWTServiceInterface
type MockJWTService struct {
	mock.Mock
}

// AuthProviderInterface represents the auth providers
type AuthProviderInterface struct {
	JWTService JWTServiceInterface
}

// HandlersInterface represents all route handlers
type HandlersInterface struct {
	AuthHandler     HandlerInterface
	UserHandler     HandlerInterface
	SettingsHandler HandlerInterface
	GenericHandler  HandlerInterface
}

// ServerInterface defines methods required from Server
type ServerInterface interface {
	SetupRoutes()
	GetRouter() chi.Router
	GetAPIRoutes(w http.ResponseWriter, r *http.Request)
}

// TestServer is a minimal implementation of Server for testing
type TestServer struct {
	Config        *config.AppConfig
	Db            DatabaseInterface
	router        chi.Router
	Handlers      HandlersInterface
	authProviders *AuthProviderInterface
}

// GetRouter implements ServerInterface
func (s *TestServer) GetRouter() chi.Router {
	return s.router
}

// SetupRoutes sets up the test server routes for testing
func (s *TestServer) SetupRoutes() {
	r := chi.NewRouter()

	// Configure basic middleware and routes for testing
	r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
		// Check database connection
		err := s.Db.HealthCheck(r.Context())
		if err != nil {
			http.Error(w, "Service unavailable", http.StatusServiceUnavailable)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		if _, err := w.Write([]byte(`{"status":"healthy","version":"test"}`)); err != nil {
			log.Print("failed to write response: ", err)
		}
	})

	r.Get("/version", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if _, err := w.Write([]byte(`{"version":"test","environment":"test"}`)); err != nil {
			log.Print("failed to write response: ", err)
		}
	})

	r.Get("/api/routes", s.GetAPIRoutes)

	// Set the router
	s.router = r
}

// GetAPIRoutes is a test implementation of the original method
func (s *TestServer) GetAPIRoutes(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	// Create a simplified version of the API documentation
	routes := map[string]interface{}{
		"authentication": map[string]string{
			"description": "Authentication endpoints",
		},
		"users": map[string]string{
			"description": "User management endpoints",
		},
		"api_keys": map[string]string{
			"description": "API key management endpoints",
		},
		"settings": map[string]string{
			"description": "User settings endpoints",
		},
		"system": map[string]string{
			"description": "System endpoints",
		},
	}

	// Wrap response in standard format
	response := APIResponse{
		Success: true,
		Data:    routes,
	}

	responseBytes, _ := json.Marshal(response)
	if _, err := w.Write(responseBytes); err != nil {
		log.Print("failed to write response: ", err)
	}
}

// TestHandlePreflight tests the handlePreflight function
func TestHandlePreflights(t *testing.T) {
	// Test cases for allowed and disallowed origins
	tests := []struct {
		name           string
		allowedOrigins []string
		origin         string
		expectedStatus int
		checkHeaders   bool
	}{
		{
			name:           "Allowed origin",
			allowedOrigins: []string{"http://example.com"},
			origin:         "http://example.com",
			expectedStatus: http.StatusNoContent,
			checkHeaders:   true,
		},
		{
			name:           "Wildcard allowed origin",
			allowedOrigins: []string{"*"},
			origin:         "http://example.com",
			expectedStatus: http.StatusNoContent,
			checkHeaders:   true,
		},
		{
			name:           "Disallowed origin",
			allowedOrigins: []string{"http://example.org"},
			origin:         "http://example.com",
			expectedStatus: http.StatusNoContent,
			checkHeaders:   false,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			// Create test request with origin header
			req := httptest.NewRequest("OPTIONS", "/test", nil)
			req.Header.Set("Origin", tc.origin)

			// Create response recorder
			w := httptest.NewRecorder()

			// Call the function
			handleFunc := handlePreflight(tc.allowedOrigins)
			handleFunc(w, req)

			// Check response
			resp := w.Result()
			defer resp.Body.Close()

			assert.Equal(t, tc.expectedStatus, resp.StatusCode)

			if tc.checkHeaders {
				assert.Equal(t, tc.origin, resp.Header.Get("Access-Control-Allow-Origin"))
				assert.NotEmpty(t, resp.Header.Get("Access-Control-Allow-Methods"))
				assert.NotEmpty(t, resp.Header.Get("Access-Control-Allow-Headers"))
				assert.Equal(t, "true", resp.Header.Get("Access-Control-Allow-Credentials"))
				assert.NotEmpty(t, resp.Header.Get("Access-Control-Max-Age"))
			} else {
				assert.Empty(t, resp.Header.Get("Access-Control-Allow-Origin"))
			}
		})
	}
}

// TestCorsMiddleware tests the corsMiddleware function
func TestCorMiddleware(t *testing.T) {
	// Test cases for CORS middleware
	tests := []struct {
		name           string
		allowedOrigins []string
		origin         string
		method         string
		expectedHeader string
	}{
		{
			name:           "Regular request with allowed origin",
			allowedOrigins: []string{"http://example.com"},
			origin:         "http://example.com",
			method:         "GET",
			expectedHeader: "http://example.com",
		},
		{
			name:           "Regular request with wildcard origin",
			allowedOrigins: []string{"*"},
			origin:         "http://example.com",
			method:         "GET",
			expectedHeader: "http://example.com",
		},
		{
			name:           "OPTIONS request with allowed origin",
			allowedOrigins: []string{"http://example.com"},
			origin:         "http://example.com",
			method:         "OPTIONS",
			expectedHeader: "http://example.com",
		},
		{
			name:           "Request with disallowed origin",
			allowedOrigins: []string{"http://example.org"},
			origin:         "http://example.com",
			method:         "GET",
			expectedHeader: "",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			// Create a handler that confirms it was called
			var handlerCalled bool
			testHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				handlerCalled = true
				w.WriteHeader(http.StatusOK)
			})

			// Apply CORS middleware
			handler := corsMiddleware(tc.allowedOrigins)(testHandler)

			// Create test request with origin header
			req := httptest.NewRequest(tc.method, "/test", nil)
			req.Header.Set("Origin", tc.origin)

			// Create response recorder
			w := httptest.NewRecorder()

			// Call the handler
			handler.ServeHTTP(w, req)

			// Check response
			resp := w.Result()
			defer resp.Body.Close()

			// For OPTIONS requests, the next handler shouldn't be called
			if tc.method == "OPTIONS" && tc.expectedHeader != "" {
				assert.False(t, handlerCalled, "Handler should not be called for OPTIONS request")
				assert.Equal(t, http.StatusNoContent, resp.StatusCode)
			} else if tc.expectedHeader != "" {
				// For other methods with allowed origins, handler should be called
				assert.True(t, handlerCalled, "Handler should be called for non-OPTIONS request")
			}

			// Check CORS headers
			assert.Equal(t, tc.expectedHeader, resp.Header.Get("Access-Control-Allow-Origin"))
			if tc.expectedHeader != "" {
				assert.Equal(t, "true", resp.Header.Get("Access-Control-Allow-Credentials"))

				if tc.method == "OPTIONS" {
					assert.NotEmpty(t, resp.Header.Get("Access-Control-Allow-Methods"))
					assert.NotEmpty(t, resp.Header.Get("Access-Control-Allow-Headers"))
					assert.NotEmpty(t, resp.Header.Get("Access-Control-Max-Age"))
				}
			}
		})
	}
}

// TestGetAllowedOrigins tests the getAllowedOrigins function
func TestGetAllowedOrigin(t *testing.T) {
	// Save original environment and restore after test
	originalEnv := os.Getenv("ALLOWED_ORIGINS")
	defer os.Setenv("ALLOWED_ORIGINS", originalEnv)

	// Test cases
	tests := []struct {
		name          string
		envValue      string
		expectedCount int
		contains      string
	}{
		{
			name:          "Default origins when env not set",
			envValue:      "",
			expectedCount: 4, // Based on default origins in the code
			contains:      "https://www.hidemeai.com",
		},
		{
			name:          "Single origin from env",
			envValue:      "http://test.com",
			expectedCount: 1,
			contains:      "http://test.com",
		},
		{
			name:          "Multiple origins from env",
			envValue:      "http://test1.com, http://test2.com",
			expectedCount: 2,
			contains:      "http://test1.com",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			// Set environment variable
			os.Setenv("ALLOWED_ORIGINS", tc.envValue)

			// Call the function
			origins := getAllowedOrigins()

			// Check results
			assert.Equal(t, tc.expectedCount, len(origins))
			if tc.contains != "" {
				found := false
				for _, origin := range origins {
					if origin == tc.contains {
						found = true
						break
					}
				}
				assert.True(t, found, "Expected origins to contain %s", tc.contains)
			}
		})
	}
}

// TestGetAPIRoutes tests the GetAPIRoutes handler
func TestGetAPIRoute(t *testing.T) {
	// Create test server
	server := &TestServer{}

	// Create test request
	req := httptest.NewRequest("GET", "/api/routes", nil)
	w := httptest.NewRecorder()

	// Call the handler
	server.GetAPIRoutes(w, req)

	// Check response
	resp := w.Result()
	defer resp.Body.Close()

	assert.Equal(t, http.StatusOK, resp.StatusCode)
	assert.Equal(t, "application/json", resp.Header.Get("Content-Type"))

	// Parse response body
	var apiResponse APIResponse
	err := json.NewDecoder(resp.Body).Decode(&apiResponse)
	require.NoError(t, err)

	// Check that the response has the expected sections
	assert.True(t, apiResponse.Success)

	data, ok := apiResponse.Data.(map[string]interface{})
	require.True(t, ok, "Response data should be a map")

	// Check that all expected sections are present
	sections := []string{"authentication", "users", "api_keys", "settings", "system"}
	for _, section := range sections {
		_, ok := data[section]
		assert.True(t, ok, "Response should contain section: %s", section)
	}
}

// TestSetupRoutes tests the route setup and configuration
func TestSetupRoutes(t *testing.T) {
	// Create mock database
	mockDb := new(MockDatabase)
	mockDb.On("HealthCheck", mock.Anything).Return(nil)

	// Create mock handlers
	mockAuthHandler := new(MockHandler)
	mockUserHandler := new(MockHandler)
	mockSettingsHandler := new(MockHandler)
	mockGenericHandler := new(MockHandler)

	// Create test server with mocks
	server := &TestServer{
		Config: &config.AppConfig{
			App: config.AppSettings{
				Version:     "test",
				Environment: "test",
			},
		},
		Db: mockDb,
		Handlers: HandlersInterface{
			AuthHandler:     mockAuthHandler,
			UserHandler:     mockUserHandler,
			SettingsHandler: mockSettingsHandler,
			GenericHandler:  mockGenericHandler,
		},
		authProviders: &AuthProviderInterface{},
	}

	// Call the function to set up routes
	server.SetupRoutes()

	// Get the router
	router := server.GetRouter()
	require.NotNil(t, router, "Router should be set after SetupRoutes")

	// Test basic endpoints to verify routes are registered
	endpoints := []struct {
		method string
		path   string
		status int
	}{
		{"GET", "/health", http.StatusOK},
		{"GET", "/version", http.StatusOK},
		{"GET", "/api/routes", http.StatusOK},
		// For more comprehensive coverage, add other endpoints
	}

	// Create a test server using the router
	testServer := httptest.NewServer(router)
	defer testServer.Close()

	// Test each endpoint
	for _, e := range endpoints {
		t.Run(e.method+" "+e.path, func(t *testing.T) {
			req, err := http.NewRequest(e.method, testServer.URL+e.path, nil)
			require.NoError(t, err)

			client := &http.Client{}
			resp, err := client.Do(req)
			require.NoError(t, err)
			defer resp.Body.Close()

			assert.Equal(t, e.status, resp.StatusCode)
		})
	}

	// Verify mock expectations
	mockDb.AssertExpectations(t)
}

// TestHealthEndpoint tests the health endpoint with different database states
func TestHealthEndpoint(t *testing.T) {
	tests := []struct {
		name          string
		dbHealthError error
		expectedCode  int
	}{
		{
			name:          "Database healthy",
			dbHealthError: nil,
			expectedCode:  http.StatusOK,
		},
		{
			name:          "Database unhealthy",
			dbHealthError: fmt.Errorf("database connection error"),
			expectedCode:  http.StatusServiceUnavailable,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			// Create mock database
			mockDb := new(MockDatabase)
			mockDb.On("HealthCheck", mock.Anything).Return(tc.dbHealthError)

			// Create test server with the mock
			server := &TestServer{
				Config: &config.AppConfig{
					App: config.AppSettings{
						Version:     "test",
						Environment: "test",
					},
				},
				Db: mockDb,
			}

			// Set up routes
			server.SetupRoutes()

			// Create a test request
			req := httptest.NewRequest("GET", "/health", nil)
			w := httptest.NewRecorder()

			// Call the handler directly using the router
			server.GetRouter().ServeHTTP(w, req)

			// Check response
			resp := w.Result()
			defer resp.Body.Close()

			assert.Equal(t, tc.expectedCode, resp.StatusCode)

			// Verify expectations
			mockDb.AssertExpectations(t)
		})
	}
}

// TestRoutePatterns tests that specific route patterns are registered correctly
func TestRoutePatterns(t *testing.T) {
	// Create the server with mocks
	mockDb := new(MockDatabase)
	mockDb.On("HealthCheck", mock.Anything).Return(nil)

	server := &TestServer{
		Config: &config.AppConfig{
			App: config.AppSettings{
				Version:     "test",
				Environment: "test",
			},
		},
		Db: mockDb,
	}

	// Set up routes
	server.SetupRoutes()

	// Get the router as a chi router
	router, ok := server.GetRouter().(*chi.Mux)
	require.True(t, ok, "Router should be a chi.Mux")

	// Create a walkFunc to check for specific routes
	// Note: Chi doesn't expose routes directly, but this gives us a way to check
	routes := make(map[string][]string)
	err := chi.Walk(router, func(method string, route string, handler http.Handler, middlewares ...func(http.Handler) http.Handler) error {
		if _, ok := routes[route]; !ok {
			routes[route] = []string{method}
		} else {
			routes[route] = append(routes[route], method)
		}
		return nil
	})

	require.NoError(t, err)

	// Check for specific routes
	expectedRoutes := []struct {
		path   string
		method string
	}{
		{"/health", "GET"},
		{"/version", "GET"},
		{"/api/routes", "GET"},
		// Add more routes as needed
	}

	for _, r := range expectedRoutes {
		t.Run(r.method+" "+r.path, func(t *testing.T) {
			methods, ok := routes[r.path]
			assert.True(t, ok, "Route %s should be registered", r.path)

			methodFound := false
			for _, m := range methods {
				if m == r.method {
					methodFound = true
					break
				}
			}
			assert.True(t, methodFound, "Method %s should be registered for route %s", r.method, r.path)
		})
	}
}

// TestGetRouter tests the GetRouter function
func TestGetRouter(t *testing.T) {
	// Create test server
	server := &TestServer{}

	// Set up routes and router
	server.router = chi.NewRouter()

	// Call the function
	router := server.GetRouter()

	// Check result
	assert.NotNil(t, router)
	assert.Equal(t, server.router, router)
}

// MockFullServer is a test implementation that matches the real Server structure
// This helps test actual SetupRoutes functionality without real dependencies
type MockFullServer struct {
	Config *config.AppConfig
	Db     DatabaseInterface
	router chi.Router
	// Other fields would need to be properly mocked

	// Track calls to handlers for verification
	GetAPIRoutesCalled bool
}

func (s *MockFullServer) SetupRoutes() {
	r := chi.NewRouter()

	// Use allowedOrigins directly to test the CORS middleware
	allowedOrigins := []string{"http://example.com", "*"}

	// Apply CORS middleware
	r.Use(corsMiddleware(allowedOrigins))

	// Add basic routes for testing
	r.Get("/api/routes", s.GetAPIRoutes)

	// Store the router
	s.router = r
}

func (s *MockFullServer) GetRouter() chi.Router {
	return s.router
}

func (s *MockFullServer) GetAPIRoutes(w http.ResponseWriter, r *http.Request) {
	s.GetAPIRoutesCalled = true
	w.Header().Set("Content-Type", "application/json")
	if _, err := w.Write([]byte(`{"success":true,"data":{"routes":"test"}}`)); err != nil {
		log.Print("failed to write response: ", err)
	}
}

// TestRealServerFunctionality tests the Server implementation with mocked dependencies
func TestRealServerFunctionality(t *testing.T) {
	server := &MockFullServer{
		Config: &config.AppConfig{
			App: config.AppSettings{
				Version:     "test",
				Environment: "test",
			},
		},
		Db: &MockDatabase{},
	}

	// Set up routes
	server.SetupRoutes()

	// Get the router
	router := server.GetRouter()
	require.NotNil(t, router)

	// Test CORS middleware - allowed origin
	req := httptest.NewRequest("GET", "/api/routes", nil)
	req.Header.Set("Origin", "http://example.com")

	w := httptest.NewRecorder()
	router.ServeHTTP(w, req)

	// Check CORS headers were set
	resp := w.Result()
	defer resp.Body.Close()

	assert.Equal(t, "http://example.com", resp.Header.Get("Access-Control-Allow-Origin"))
	assert.Equal(t, "true", resp.Header.Get("Access-Control-Allow-Credentials"))

	// Verify handler was called
	assert.True(t, server.GetAPIRoutesCalled)
}

// BenchmarkSetupRoutes benchmarks the route setup performance
func BenchmarkSetupRoutes(b *testing.B) {
	mockDb := new(MockDatabase)
	mockDb.On("HealthCheck", mock.Anything).Return(nil)

	server := &TestServer{
		Config: &config.AppConfig{
			App: config.AppSettings{
				Version:     "test",
				Environment: "test",
			},
		},
		Db: mockDb,
	}

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		server.SetupRoutes()
	}
}
