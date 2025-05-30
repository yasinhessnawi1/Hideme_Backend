package middleware_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/middleware"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// MockJWTService is a complete mock implementation of auth.JWTService
type MockJWTService struct {
	Config                          *config.JWTSettings
	ValidateTokenFunc               func(tokenString string, expectedType string) (*auth.CustomClaims, error)
	ParseTokenWithoutValidationFunc func(tokenString string) (string, error)
	GenerateAccessTokenFunc         func(userID int64, username, email string) (string, string, error)
	GenerateRefreshTokenFunc        func(userID int64, username, email string) (string, string, error)
	ExtractUserIDFromTokenFunc      func(tokenString string) (int64, error)
	RefreshTokensFunc               func(refreshToken, userID int64, username, email string) (string, string, string, string, error)
	GetConfigFunc                   func() *config.JWTSettings
}

// ValidateToken implements the interface method
func (m *MockJWTService) ValidateToken(tokenString string, expectedType string) (*auth.CustomClaims, error) {
	return m.ValidateTokenFunc(tokenString, expectedType)
}

// ParseTokenWithoutValidation implements the interface method
func (m *MockJWTService) ParseTokenWithoutValidation(tokenString string) (string, error) {
	if m.ParseTokenWithoutValidationFunc != nil {
		return m.ParseTokenWithoutValidationFunc(tokenString)
	}
	return "", errors.New("not implemented")
}

// GenerateAccessToken implements the interface method
func (m *MockJWTService) GenerateAccessToken(userID int64, username, email string) (string, string, error) {
	if m.GenerateAccessTokenFunc != nil {
		return m.GenerateAccessTokenFunc(userID, username, email)
	}
	return "", "", errors.New("not implemented")
}

// GenerateRefreshToken implements the interface method
func (m *MockJWTService) GenerateRefreshToken(userID int64, username, email string) (string, string, error) {
	if m.GenerateRefreshTokenFunc != nil {
		return m.GenerateRefreshTokenFunc(userID, username, email)
	}
	return "", "", errors.New("not implemented")
}

// ExtractUserIDFromToken implements the interface method
func (m *MockJWTService) ExtractUserIDFromToken(tokenString string) (int64, error) {
	if m.ExtractUserIDFromTokenFunc != nil {
		return m.ExtractUserIDFromTokenFunc(tokenString)
	}
	return 0, errors.New("not implemented")
}

// RefreshTokens implements the interface method
func (m *MockJWTService) RefreshTokens(refreshToken, userID int64, username, email string) (string, string, string, string, error) {
	if m.RefreshTokensFunc != nil {
		return m.RefreshTokensFunc(refreshToken, userID, username, email)
	}
	return "", "", "", "", errors.New("not implemented")
}

// GetConfig implements the interface method
func (m *MockJWTService) GetConfig() *config.JWTSettings {
	if m.GetConfigFunc != nil {
		return m.GetConfigFunc()
	}
	return m.Config
}

// MockHandler is a simple http.Handler implementation for testing middleware
type MockHandler struct {
	Called     bool
	StatusCode int
	Response   string
	Headers    map[string]string
}

func (m *MockHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	m.Called = true

	// Set custom headers if specified
	for key, value := range m.Headers {
		w.Header().Set(key, value)
	}

	if m.StatusCode != 0 {
		w.WriteHeader(m.StatusCode)
	}

	if m.Response != "" {
		if _, err := w.Write([]byte(m.Response)); err != nil {
			panic(err)
		}
	}
}

// Define a custom type for context keys
type contextKeyUserRole struct{}

func TestJWTAuth(t *testing.T) {
	tests := []struct {
		name            string
		setupAuth       func() *MockJWTService
		authHeader      string
		cookie          *http.Cookie
		expectedStatus  int
		shouldCallNext  bool
		expectedUserID  int64
		expectedContext map[auth.ContextKey]interface{}
	}{

		{
			name: "Missing Authorization header",
			setupAuth: func() *MockJWTService {
				return &MockJWTService{
					Config: &config.JWTSettings{},
					ValidateTokenFunc: func(tokenString string, expectedType string) (*auth.CustomClaims, error) {
						return nil, errors.New("invalid token")
					},
				}
			},
			expectedStatus: http.StatusUnauthorized,
			shouldCallNext: false,
		},
		{
			name: "Invalid Bearer format",
			setupAuth: func() *MockJWTService {
				return &MockJWTService{
					Config: &config.JWTSettings{},
					ValidateTokenFunc: func(tokenString string, expectedType string) (*auth.CustomClaims, error) {
						return nil, errors.New("invalid token")
					},
				}
			},
			authHeader:     "NotBearer valid-token",
			expectedStatus: http.StatusUnauthorized,
			shouldCallNext: false,
		},
		{
			name: "Invalid token",
			setupAuth: func() *MockJWTService {
				return &MockJWTService{
					Config: &config.JWTSettings{},
					ValidateTokenFunc: func(tokenString string, expectedType string) (*auth.CustomClaims, error) {
						return nil, utils.NewInvalidTokenError()
					},
				}
			},
			authHeader:     "Bearer invalid-token",
			expectedStatus: http.StatusUnauthorized,
			shouldCallNext: false,
		},
		{
			name: "Expired token",
			setupAuth: func() *MockJWTService {
				return &MockJWTService{
					Config: &config.JWTSettings{},
					ValidateTokenFunc: func(tokenString string, expectedType string) (*auth.CustomClaims, error) {
						return nil, utils.NewExpiredTokenError()
					},
				}
			},
			authHeader:     "Bearer expired-token",
			expectedStatus: http.StatusUnauthorized,
			shouldCallNext: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create a mock JWT service
			mockJWT := tt.setupAuth()

			// Create a mock handler to verify it gets called
			mockHandler := &MockHandler{}

			// Create the middleware
			middleware := middleware.JWTAuth(mockJWT)(mockHandler)

			// Create a test request
			req, err := http.NewRequest("GET", "/test", nil)
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}

			// Add authorization header if provided
			if tt.authHeader != "" {
				req.Header.Set("Authorization", tt.authHeader)
			}

			// Add cookie if provided
			if tt.cookie != nil {
				req.AddCookie(tt.cookie)
			}

			// Add a request ID to the context to simulate previous middleware
			ctx := context.WithValue(req.Context(), auth.RequestIDContextKey, "test-request-id")
			req = req.WithContext(ctx)

			// Create a response recorder
			rr := httptest.NewRecorder()

			// Call the middleware
			middleware.ServeHTTP(rr, req)

			// Check status code
			if status := rr.Code; status != tt.expectedStatus {
				t.Errorf("Handler returned wrong status code: got %v want %v", status, tt.expectedStatus)
			}

			// Check if next handler was called
			if mockHandler.Called != tt.shouldCallNext {
				t.Errorf("Next handler called = %v, want %v", mockHandler.Called, tt.shouldCallNext)
			}

			// Check context values if next handler was called
			if tt.shouldCallNext {
				for key, expected := range tt.expectedContext {
					actual := req.Context().Value(key)
					if actual != expected {
						t.Errorf("Context value %v = %v, want %v", key, actual, expected)
					}
				}
			}
		})
	}
}

func TestAPIKeyAuth(t *testing.T) {
	tests := []struct {
		name           string
		apiKeyHeader   string
		expectedStatus int
		shouldCallNext bool
	}{
		{
			name:           "Valid API key",
			apiKeyHeader:   "valid-api-key",
			expectedStatus: http.StatusOK,
			shouldCallNext: true,
		},
		{
			name:           "Missing API key",
			apiKeyHeader:   "",
			expectedStatus: http.StatusUnauthorized,
			shouldCallNext: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create a mock handler to verify it gets called
			mockHandler := &MockHandler{}

			// Create the middleware
			middleware := middleware.APIKeyAuth()(mockHandler)

			// Create a test request
			req, err := http.NewRequest("GET", "/test", nil)
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}

			// Add API key header if provided
			if tt.apiKeyHeader != "" {
				req.Header.Set("X-API-Key", tt.apiKeyHeader)
			}

			// Create a response recorder
			rr := httptest.NewRecorder()

			// Call the middleware
			middleware.ServeHTTP(rr, req)

			// Check status code
			if status := rr.Code; status != tt.expectedStatus {
				t.Errorf("Handler returned wrong status code: got %v want %v", status, tt.expectedStatus)
			}

			// Check if next handler was called
			if mockHandler.Called != tt.shouldCallNext {
				t.Errorf("Next handler called = %v, want %v", mockHandler.Called, tt.shouldCallNext)
			}
		})
	}
}

func TestRequireRole(t *testing.T) {
	tests := []struct {
		name           string
		role           string
		setupContext   func(r *http.Request) *http.Request
		expectedStatus int
		shouldCallNext bool
	}{
		/*
			{
				name: "User has required role",
				role: "admin",
				setupContext: func(r *http.Request) *http.Request {
					ctx := context.WithValue(r.Context(), auth.UserIDContextKey, int64(123))
					ctx = context.WithValue(ctx, contextKeyUserRole{}, "admin") // Add role to context
					return r.WithContext(ctx)
				},
				expectedStatus: http.StatusOK,
				shouldCallNext: true,
			},

		*/
		{
			name: "User not authenticated",
			role: "admin",
			setupContext: func(r *http.Request) *http.Request {
				return r
			},
			expectedStatus: http.StatusUnauthorized,
			shouldCallNext: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create a mock handler to verify it gets called
			mockHandler := &MockHandler{}

			// Create the middleware
			middleware := middleware.RequireRole(tt.role)(mockHandler)

			// Create a test request
			req, err := http.NewRequest("GET", "/test", nil)
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}

			// Setup context
			req = tt.setupContext(req)

			// Create a response recorder
			rr := httptest.NewRecorder()

			// Call the middleware
			middleware.ServeHTTP(rr, req)

			// Check status code
			if status := rr.Code; status != tt.expectedStatus {
				t.Errorf("Handler returned wrong status code: got %v want %v", status, tt.expectedStatus)
			}

			// Check if next handler was called
			if mockHandler.Called != tt.shouldCallNext {
				t.Errorf("Next handler called = %v, want %v", mockHandler.Called, tt.shouldCallNext)
			}
		})
	}
}

func TestCSRF(t *testing.T) {
	tests := []struct {
		name           string
		method         string
		csrfToken      string
		csrfCookie     *http.Cookie
		expectedStatus int
		shouldCallNext bool
	}{
		{
			name:           "GET request bypasses CSRF check",
			method:         "GET",
			expectedStatus: http.StatusOK,
			shouldCallNext: true,
		},
		{
			name:           "HEAD request bypasses CSRF check",
			method:         "HEAD",
			expectedStatus: http.StatusOK,
			shouldCallNext: true,
		},
		{
			name:           "OPTIONS request bypasses CSRF check",
			method:         "OPTIONS",
			expectedStatus: http.StatusOK,
			shouldCallNext: true,
		},
		{
			name:           "POST request with valid CSRF token",
			method:         "POST",
			csrfToken:      "valid-csrf-token",
			csrfCookie:     &http.Cookie{Name: "csrf_token", Value: "valid-csrf-token"},
			expectedStatus: http.StatusOK,
			shouldCallNext: true,
		},
		{
			name:           "POST request with missing CSRF token",
			method:         "POST",
			csrfCookie:     &http.Cookie{Name: "csrf_token", Value: "valid-csrf-token"},
			expectedStatus: http.StatusForbidden,
			shouldCallNext: false,
		},
		{
			name:           "POST request with mismatched CSRF token",
			method:         "POST",
			csrfToken:      "invalid-csrf-token",
			csrfCookie:     &http.Cookie{Name: "csrf_token", Value: "valid-csrf-token"},
			expectedStatus: http.StatusForbidden,
			shouldCallNext: false,
		},
		{
			name:           "POST request with missing CSRF cookie",
			method:         "POST",
			csrfToken:      "valid-csrf-token",
			expectedStatus: http.StatusForbidden,
			shouldCallNext: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create a mock handler to verify it gets called
			mockHandler := &MockHandler{}

			// Create the middleware
			middleware := middleware.CSRF()(mockHandler)

			// Create a test request
			req, err := http.NewRequest(tt.method, "/test", nil)
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}

			// Add CSRF token header if provided
			if tt.csrfToken != "" {
				req.Header.Set("X-CSRF-Token", tt.csrfToken)
			}

			// Add CSRF cookie if provided
			if tt.csrfCookie != nil {
				req.AddCookie(tt.csrfCookie)
			}

			// Create a response recorder
			rr := httptest.NewRecorder()

			// Call the middleware
			middleware.ServeHTTP(rr, req)

			// Check status code
			if status := rr.Code; status != tt.expectedStatus {
				t.Errorf("Handler returned wrong status code: got %v want %v", status, tt.expectedStatus)
			}

			// Check if next handler was called
			if mockHandler.Called != tt.shouldCallNext {
				t.Errorf("Next handler called = %v, want %v", mockHandler.Called, tt.shouldCallNext)
			}
		})
	}
}

func TestRateLimit(t *testing.T) {
}

func TestSecurityHeaders(t *testing.T) {
	// Expected headers that should be set by the middleware
	expectedHeaders := map[string]string{
		"X-Content-Type-Options":  "nosniff",
		"X-Frame-Options":         "DENY",
		"X-XSS-Protection":        "1; mode=block",
		"Referrer-Policy":         "strict-origin-when-cross-origin",
		"Content-Security-Policy": "default-src 'self'",
	}

	// Create a mock handler
	mockHandler := &MockHandler{
		StatusCode: http.StatusOK,
		Response:   "Success",
	}

	// Create the middleware
	middleware := middleware.SecurityHeaders()(mockHandler)

	// Create a test request
	req, err := http.NewRequest("GET", "/test", nil)
	if err != nil {
		t.Fatalf("Failed to create request: %v", err)
	}

	// Create a response recorder
	rr := httptest.NewRecorder()

	// Call the middleware
	middleware.ServeHTTP(rr, req)

	// Check if handler was called
	if !mockHandler.Called {
		t.Errorf("Next handler was not called")
	}

	// Check if all expected headers were set
	for header, expectedValue := range expectedHeaders {
		value := rr.Header().Get(header)
		if value != expectedValue {
			t.Errorf("Header %s = %s, want %s", header, value, expectedValue)
		}
	}

	// Check response status code and body
	if status := rr.Code; status != http.StatusOK {
		t.Errorf("Handler returned wrong status code: got %v want %v", status, http.StatusOK)
	}

	if body := rr.Body.String(); body != "Success" {
		t.Errorf("Handler returned unexpected body: got %v want %v", body, "Success")
	}
}
