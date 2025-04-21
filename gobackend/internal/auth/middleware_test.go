package auth_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
)

// MockJWTValidator implements the JWTValidator interface for testing
type MockJWTValidator struct {
	ValidateFunc func(string, string) (*auth.CustomClaims, error)
}

func (m *MockJWTValidator) ValidateToken(tokenString, expectedType string) (*auth.CustomClaims, error) {
	return m.ValidateFunc(tokenString, expectedType)
}

func TestGetUserID(t *testing.T) {
	// Create a request with user ID in context
	r := httptest.NewRequest("GET", "/", nil)
	ctx := context.WithValue(r.Context(), auth.UserIDContextKey, int64(123))
	r = r.WithContext(ctx)

	// Get user ID
	userID, ok := auth.GetUserID(r)

	// Check result
	if !ok {
		t.Error("Expected ok to be true")
	}

	if userID != int64(123) {
		t.Errorf("Expected userID to be 123, got %d", userID)
	}

	// Test missing user ID
	r = httptest.NewRequest("GET", "/", nil)
	userID, ok = auth.GetUserID(r)

	// Check result
	if ok {
		t.Error("Expected ok to be false")
	}

	if userID != 0 {
		t.Errorf("Expected userID to be 0, got %d", userID)
	}
}

func TestGetUsername(t *testing.T) {
	// Create a request with username in context
	r := httptest.NewRequest("GET", "/", nil)
	ctx := context.WithValue(r.Context(), auth.UsernameContextKey, "testuser")
	r = r.WithContext(ctx)

	// Get username
	username, ok := auth.GetUsername(r)

	// Check result
	if !ok {
		t.Error("Expected ok to be true")
	}

	if username != "testuser" {
		t.Errorf("Expected username to be 'testuser', got %s", username)
	}

	// Test missing username
	r = httptest.NewRequest("GET", "/", nil)
	username, ok = auth.GetUsername(r)

	// Check result
	if ok {
		t.Error("Expected ok to be false")
	}

	if username != "" {
		t.Errorf("Expected username to be empty, got %s", username)
	}
}

func TestGetEmail(t *testing.T) {
	// Create a request with email in context
	r := httptest.NewRequest("GET", "/", nil)
	ctx := context.WithValue(r.Context(), auth.EmailContextKey, "test@example.com")
	r = r.WithContext(ctx)

	// Get email
	email, ok := auth.GetEmail(r)

	// Check result
	if !ok {
		t.Error("Expected ok to be true")
	}

	if email != "test@example.com" {
		t.Errorf("Expected email to be 'test@example.com', got %s", email)
	}

	// Test missing email
	r = httptest.NewRequest("GET", "/", nil)
	email, ok = auth.GetEmail(r)

	// Check result
	if ok {
		t.Error("Expected ok to be false")
	}

	if email != "" {
		t.Errorf("Expected email to be empty, got %s", email)
	}
}

func TestGetRequestID(t *testing.T) {
	// Create a request with request ID in context
	r := httptest.NewRequest("GET", "/", nil)
	ctx := context.WithValue(r.Context(), auth.RequestIDContextKey, "req123")
	r = r.WithContext(ctx)

	// Get request ID
	requestID, ok := auth.GetRequestID(r)

	// Check result
	if !ok {
		t.Error("Expected ok to be true")
	}

	if requestID != "req123" {
		t.Errorf("Expected requestID to be 'req123', got %s", requestID)
	}

	// Test missing request ID
	r = httptest.NewRequest("GET", "/", nil)
	requestID, ok = auth.GetRequestID(r)

	// Check result
	if ok {
		t.Error("Expected ok to be false")
	}

	if requestID != "" {
		t.Errorf("Expected requestID to be empty, got %s", requestID)
	}
}

func TestIsAuthenticated(t *testing.T) {
	// Create a request with user ID in context
	r := httptest.NewRequest("GET", "/", nil)
	ctx := context.WithValue(r.Context(), auth.UserIDContextKey, int64(123))
	r = r.WithContext(ctx)

	// Check if authenticated
	authenticated := auth.IsAuthenticated(r)

	// Check result
	if !authenticated {
		t.Error("Expected authenticated to be true")
	}

	// Test unauthenticated
	r = httptest.NewRequest("GET", "/", nil)
	authenticated = auth.IsAuthenticated(r)

	// Check result
	if authenticated {
		t.Error("Expected authenticated to be false")
	}
}

func TestJWTAuthProvider_Authenticate(t *testing.T) {

}

func TestAuthMiddleware(t *testing.T) {
	// Create mock provider that succeeds
	successProvider := &MockAuthProvider{
		AuthenticateFunc: func(r *http.Request) (int64, string, string, error) {
			return 123, "testuser", "test@example.com", nil
		},
	}

	// Create mock provider that fails
	failProvider := &MockAuthProvider{
		AuthenticateFunc: func(r *http.Request) (int64, string, string, error) {
			return 0, "", "", fmt.Errorf("authentication failed")
		},
	}

	// Create a mock handler to check if it gets called
	var handlerCalled bool
	nextHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handlerCalled = true

		// Check context values
		userID, ok := auth.GetUserID(r)
		if !ok || userID != 123 {
			t.Errorf("Expected userID 123 in context, got %v", userID)
		}

		username, ok := auth.GetUsername(r)
		if !ok || username != "testuser" {
			t.Errorf("Expected username 'testuser' in context, got %v", username)
		}

		email, ok := auth.GetEmail(r)
		if !ok || email != "test@example.com" {
			t.Errorf("Expected email 'test@example.com' in context, got %v", email)
		}

		w.WriteHeader(http.StatusOK)
	})

	// Test successful authentication
	handlerCalled = false
	middleware := auth.AuthMiddleware(nextHandler, successProvider)

	r := httptest.NewRequest("GET", "/", nil)
	r.Header.Set("X-Request-ID", "req123")
	w := httptest.NewRecorder()

	middleware.ServeHTTP(w, r)

	// Check that handler was called
	if !handlerCalled {
		t.Error("Expected handler to be called")
	}

	// Check status code
	if w.Code != http.StatusOK {
		t.Errorf("Expected status code %d, got %d", http.StatusOK, w.Code)
	}

	// Test failed authentication
	handlerCalled = false
	middleware = auth.AuthMiddleware(nextHandler, failProvider)

	r = httptest.NewRequest("GET", "/", nil)
	r.Header.Set("X-Request-ID", "req123")
	w = httptest.NewRecorder()

	middleware.ServeHTTP(w, r)

	// Check that handler was not called
	if handlerCalled {
		t.Error("Expected handler not to be called")
	}

	// Check status code (should be unauthorized)
	if w.Code != http.StatusUnauthorized {
		t.Errorf("Expected status code %d, got %d", http.StatusUnauthorized, w.Code)
	}
}

// MockAuthProvider implements the AuthProvider interface for testing
type MockAuthProvider struct {
	AuthenticateFunc func(r *http.Request) (int64, string, string, error)
}

func (m *MockAuthProvider) Authenticate(r *http.Request) (int64, string, string, error) {
	return m.AuthenticateFunc(r)
}

func TestRequireAuth(t *testing.T) {
	// This is a wrapper around AuthMiddleware, so a simple test is sufficient
	provider := &MockAuthProvider{
		AuthenticateFunc: func(r *http.Request) (int64, string, string, error) {
			return 123, "testuser", "test@example.com", nil
		},
	}

	var handlerCalled bool
	nextHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handlerCalled = true
		w.WriteHeader(http.StatusOK)
	})

	// Create middleware
	middleware := auth.RequireAuth(provider)(nextHandler)

	// Test
	r := httptest.NewRequest("GET", "/", nil)
	w := httptest.NewRecorder()

	middleware.ServeHTTP(w, r)

	// Check that handler was called
	if !handlerCalled {
		t.Error("Expected handler to be called")
	}
}

func TestOptionalAuth(t *testing.T) {
	// Create mock provider that fails
	failProvider := &MockAuthProvider{
		AuthenticateFunc: func(r *http.Request) (int64, string, string, error) {
			return 0, "", "", fmt.Errorf("authentication failed")
		},
	}

	var handlerCalled bool
	nextHandler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		handlerCalled = true

		// Should still be called even if auth fails
		w.WriteHeader(http.StatusOK)
	})

	// Create middleware
	middleware := auth.OptionalAuth(failProvider)(nextHandler)

	// Test
	r := httptest.NewRequest("GET", "/", nil)
	w := httptest.NewRecorder()

	middleware.ServeHTTP(w, r)

	// Check that handler was called despite auth failure
	if !handlerCalled {
		t.Error("Expected handler to be called")
	}

	// Check status code
	if w.Code != http.StatusOK {
		t.Errorf("Expected status code %d, got %d", http.StatusOK, w.Code)
	}
}
