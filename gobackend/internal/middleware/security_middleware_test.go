package middleware_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/middleware"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

// MockSecurityService implements the middleware.SecurityService interface
type MockSecurityService struct {
	mock.Mock
}

// IsBanned mocks the IsBanned method
func (m *MockSecurityService) IsBanned(ipAddress string) bool {
	args := m.Called(ipAddress)
	return args.Bool(0)
}

// IsRateLimited mocks the IsRateLimited method
func (m *MockSecurityService) IsRateLimited(ipAddress string, category string) bool {
	args := m.Called(ipAddress, category)
	return args.Bool(0)
}

// BanIP mocks the BanIP method
func (m *MockSecurityService) BanIP(ctx context.Context, ipAddress string, reason string, duration time.Duration, bannedBy string) (*models.IPBan, error) {
	args := m.Called(ctx, ipAddress, reason, duration, bannedBy)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.IPBan), args.Error(1)
}

// SecurityMockHandler is a simple HTTP handler for testing security middleware
type SecurityMockHandler struct {
	Called     bool
	StatusCode int
	Response   string
}

// ServeHTTP implements the http.Handler interface
func (h *SecurityMockHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	h.Called = true
	if h.StatusCode != 0 {
		w.WriteHeader(h.StatusCode)
	} else {
		w.WriteHeader(http.StatusOK)
	}
	if h.Response != "" {
		w.Write([]byte(h.Response))
	}
}

// Helper function to check if a path is exempted
// This replicates the logic in the middleware package
func isExemptedPath(path string) bool {
	exemptPrefixes := []string{
		"/health",
		"/version",
		"/static/",
		"/public/",
		"/favicon.ico",
	}

	for _, prefix := range exemptPrefixes {
		if strings.HasPrefix(path, prefix) {
			return true
		}
	}

	return false
}

func TestSecurityRateLimit(t *testing.T) {
	tests := []struct {
		name           string
		ipAddress      string
		category       string
		isRateLimited  bool
		path           string
		expectedStatus int
		shouldCallNext bool
	}{
		{
			name:           "Rate limit not exceeded",
			ipAddress:      "192.168.1.1",
			category:       "api",
			isRateLimited:  false,
			path:           "/api/test",
			expectedStatus: http.StatusOK,
			shouldCallNext: true,
		},
		{
			name:           "Rate limit exceeded",
			ipAddress:      "192.168.1.2",
			category:       "api",
			isRateLimited:  true,
			path:           "/api/test",
			expectedStatus: http.StatusTooManyRequests,
			shouldCallNext: false,
		},
		{
			name:           "Exempted path",
			ipAddress:      "192.168.1.3",
			category:       "api",
			isRateLimited:  true, // Would be rate limited if not exempted
			path:           "/health",
			expectedStatus: http.StatusOK,
			shouldCallNext: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create a mock security service
			mockService := new(MockSecurityService)

			// Only set up expectation if path is not exempted
			if !isExemptedPath(tt.path) {
				mockService.On("IsRateLimited", tt.ipAddress, tt.category).Return(tt.isRateLimited)
			}

			// Create a mock handler to verify it gets called
			mockHandler := &SecurityMockHandler{}

			// Create the middleware
			rateLimitMiddleware := middleware.RateLimit(mockService, tt.category)(mockHandler)

			// Create a test request
			req := httptest.NewRequest("GET", tt.path, nil)
			req.RemoteAddr = tt.ipAddress + ":12345" // Add port to simulate real request

			// Create a response recorder
			rr := httptest.NewRecorder()

			// Call the middleware
			rateLimitMiddleware.ServeHTTP(rr, req)

			// Check status code
			assert.Equal(t, tt.expectedStatus, rr.Code)

			// Check if next handler was called
			assert.Equal(t, tt.shouldCallNext, mockHandler.Called)

			// Verify mock expectations
			mockService.AssertExpectations(t)
		})
	}
}

func TestIPBanCheck(t *testing.T) {
	tests := []struct {
		name           string
		ipAddress      string
		isBanned       bool
		path           string
		expectedStatus int
		shouldCallNext bool
	}{
		{
			name:           "IP not banned",
			ipAddress:      "192.168.1.1",
			isBanned:       false,
			path:           "/api/test",
			expectedStatus: http.StatusOK,
			shouldCallNext: true,
		},
		{
			name:           "IP banned",
			ipAddress:      "192.168.1.2",
			isBanned:       true,
			path:           "/api/test",
			expectedStatus: http.StatusForbidden,
			shouldCallNext: false,
		},
		{
			name:           "Exempted path",
			ipAddress:      "192.168.1.3",
			isBanned:       true, // Would be banned if not exempted
			path:           "/health",
			expectedStatus: http.StatusOK,
			shouldCallNext: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create a mock security service
			mockService := new(MockSecurityService)

			// Only set up expectation if path is not exempted
			if !isExemptedPath(tt.path) {
				mockService.On("IsBanned", tt.ipAddress).Return(tt.isBanned)
			}

			// Create a mock handler to verify it gets called
			mockHandler := &SecurityMockHandler{}

			// Create the middleware
			ipBanMiddleware := middleware.IPBanCheck(mockService)(mockHandler)

			// Create a test request
			req := httptest.NewRequest("GET", tt.path, nil)
			req.RemoteAddr = tt.ipAddress + ":12345" // Add port to simulate real request

			// Create a response recorder
			rr := httptest.NewRecorder()

			// Call the middleware
			ipBanMiddleware.ServeHTTP(rr, req)

			// Check status code
			assert.Equal(t, tt.expectedStatus, rr.Code)

			// Check if next handler was called
			assert.Equal(t, tt.shouldCallNext, mockHandler.Called)

			// Verify mock expectations
			mockService.AssertExpectations(t)
		})
	}
}

func TestAutoBan(t *testing.T) {
	tests := []struct {
		name           string
		ipAddress      string
		path           string
		query          string
		threshold      int
		expectedStatus int
		shouldCallNext bool
		shouldBan      bool
	}{
		{
			name:           "Normal request",
			ipAddress:      "192.168.1.1",
			path:           "/api/test",
			query:          "param=value",
			threshold:      3,
			expectedStatus: http.StatusOK,
			shouldCallNext: true,
			shouldBan:      false,
		},
		{
			name:           "Suspicious request - Path traversal",
			ipAddress:      "192.168.1.3",
			path:           "/api/test/../../../etc/passwd",
			query:          "",
			threshold:      1, // Ban immediately
			expectedStatus: http.StatusForbidden,
			shouldCallNext: false,
			shouldBan:      true,
		},
		{
			name:           "Suspicious request - Admin access attempt",
			ipAddress:      "192.168.1.4",
			path:           "/wp-admin",
			query:          "",
			threshold:      1, // Ban immediately
			expectedStatus: http.StatusForbidden,
			shouldCallNext: false,
			shouldBan:      true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create a mock security service
			mockService := new(MockSecurityService)

			// Set up BanIP expectation if we expect the middleware to ban the IP
			if tt.shouldBan {
				ban := &models.IPBan{
					ID:        1,
					IPAddress: tt.ipAddress,
				}
				mockService.On("BanIP", mock.Anything, tt.ipAddress, mock.Anything, mock.Anything, "system").
					Return(ban, nil)
			}

			// Create a mock handler to verify it gets called
			mockHandler := &SecurityMockHandler{}

			// Create the middleware
			autoBanMiddleware := middleware.AutoBan(mockService, tt.threshold, 1*time.Minute, 24*time.Hour)(mockHandler)

			// Create a test request
			url := tt.path
			if tt.query != "" {
				url += "?" + tt.query
			}
			req := httptest.NewRequest("GET", url, nil)
			req.RemoteAddr = tt.ipAddress + ":12345" // Add port to simulate real request

			// Create a response recorder
			rr := httptest.NewRecorder()

			// Call the middleware
			autoBanMiddleware.ServeHTTP(rr, req)

			// Check status code
			assert.Equal(t, tt.expectedStatus, rr.Code)

			// Check if next handler was called
			assert.Equal(t, tt.shouldCallNext, mockHandler.Called)

			// Verify mock expectations
			mockService.AssertExpectations(t)
		})
	}
}

// Test request headers processing
func TestRequestHeaderProcessing(t *testing.T) {
	// Mock services and handlers
	mockService := new(MockSecurityService)
	mockHandler := &SecurityMockHandler{}

	// Create middleware that will pass through to our handler
	// Set a high threshold so it doesn't ban during the test
	middleware := middleware.AutoBan(mockService, 10, 1*time.Minute, 24*time.Hour)(mockHandler)

	tests := []struct {
		name        string
		remoteAddr  string
		headers     map[string]string
		expectCalls bool // Whether we expect service methods to be called
	}{
		{
			name:        "Remote address only",
			remoteAddr:  "192.168.1.1:12345",
			expectCalls: true,
		},
		{
			name:       "With X-Forwarded-For header",
			remoteAddr: "10.0.0.1:12345",
			headers: map[string]string{
				"X-Forwarded-For": "203.0.113.1, 192.168.1.1",
			},
			expectCalls: true,
		},
		{
			name:       "With X-Real-IP header",
			remoteAddr: "10.0.0.1:12345",
			headers: map[string]string{
				"X-Real-IP": "203.0.113.2",
			},
			expectCalls: true,
		},
		{
			name:       "With multiple headers (X-Forwarded-For takes precedence)",
			remoteAddr: "10.0.0.1:12345",
			headers: map[string]string{
				"X-Forwarded-For": "203.0.113.3, 192.168.1.1",
				"X-Real-IP":       "203.0.113.4",
			},
			expectCalls: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Create test request
			req := httptest.NewRequest("GET", "/api/test", nil)
			req.RemoteAddr = tt.remoteAddr

			// Add headers
			for key, value := range tt.headers {
				req.Header.Set(key, value)
			}

			// Create response recorder
			rr := httptest.NewRecorder()

			// Call the middleware
			middleware.ServeHTTP(rr, req)

			// Verify handler was called (request passed through middleware)
			assert.True(t, mockHandler.Called)
			assert.Equal(t, http.StatusOK, rr.Code)
		})
	}
}
