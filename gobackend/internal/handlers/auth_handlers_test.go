package handlers

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// Mock AuthService that implements the interface methods required by AuthHandler
type MockAuthService struct {
	RegisterUserFunc          func(ctx context.Context, reg *models.UserRegistration) (*models.User, error)
	AuthenticateUserFunc      func(ctx context.Context, creds *models.UserCredentials) (*models.User, string, string, error)
	RefreshTokensFunc         func(ctx context.Context, refreshToken string) (string, string, error)
	LogoutFunc                func(ctx context.Context, refreshToken string) error
	LogoutAllFunc             func(ctx context.Context, userID int64) error
	CreateAPIKeyFunc          func(ctx context.Context, userID int64, name string, duration time.Duration) (string, *models.APIKey, error)
	ListAPIKeysFunc           func(ctx context.Context, userID int64) ([]*models.APIKey, error)
	DeleteAPIKeyFunc          func(ctx context.Context, userID int64, keyID string) error
	VerifyAPIKeyFunc          func(ctx context.Context, apiKeyString string) (*models.User, error)
	CleanupExpiredFunc        func(ctx context.Context) (int64, error)
	CleanupExpiredAPIKeysFunc func(ctx context.Context) (int64, error)
}

func (m *MockAuthService) RegisterUser(ctx context.Context, reg *models.UserRegistration) (*models.User, error) {
	if m.RegisterUserFunc != nil {
		return m.RegisterUserFunc(ctx, reg)
	}
	return &models.User{ID: 1, Username: reg.Username, Email: reg.Email}, nil
}

func (m *MockAuthService) AuthenticateUser(ctx context.Context, creds *models.UserCredentials) (*models.User, string, string, error) {
	if m.AuthenticateUserFunc != nil {
		return m.AuthenticateUserFunc(ctx, creds)
	}
	return &models.User{ID: 1, Username: "testuser", Email: "test@example.com"}, "access_token", "refresh_token", nil
}

func (m *MockAuthService) RefreshTokens(ctx context.Context, refreshToken string) (string, string, error) {
	if m.RefreshTokensFunc != nil {
		return m.RefreshTokensFunc(ctx, refreshToken)
	}
	return "new_access_token", "new_refresh_token", nil
}

func (m *MockAuthService) Logout(ctx context.Context, refreshToken string) error {
	if m.LogoutFunc != nil {
		return m.LogoutFunc(ctx, refreshToken)
	}
	return nil
}

func (m *MockAuthService) LogoutAll(ctx context.Context, userID int64) error {
	if m.LogoutAllFunc != nil {
		return m.LogoutAllFunc(ctx, userID)
	}
	return nil
}

func (m *MockAuthService) CreateAPIKey(ctx context.Context, userID int64, name string, duration time.Duration) (string, *models.APIKey, error) {
	if m.CreateAPIKeyFunc != nil {
		return m.CreateAPIKeyFunc(ctx, userID, name, duration)
	}
	return "raw_key", &models.APIKey{ID: "key123", UserID: userID, Name: name}, nil
}

func (m *MockAuthService) ListAPIKeys(ctx context.Context, userID int64) ([]*models.APIKey, error) {
	if m.ListAPIKeysFunc != nil {
		return m.ListAPIKeysFunc(ctx, userID)
	}
	return []*models.APIKey{{ID: "key123", UserID: userID, Name: "Test Key"}}, nil
}

func (m *MockAuthService) DeleteAPIKey(ctx context.Context, userID int64, keyID string) error {
	if m.DeleteAPIKeyFunc != nil {
		return m.DeleteAPIKeyFunc(ctx, userID, keyID)
	}
	return nil
}

func (m *MockAuthService) VerifyAPIKey(ctx context.Context, apiKeyString string) (*models.User, error) {
	if m.VerifyAPIKeyFunc != nil {
		return m.VerifyAPIKeyFunc(ctx, apiKeyString)
	}
	return &models.User{ID: 1, Username: "testuser", Email: "test@example.com"}, nil
}

func (m *MockAuthService) CleanupExpiredSessions(ctx context.Context) (int64, error) {
	if m.CleanupExpiredFunc != nil {
		return m.CleanupExpiredFunc(ctx)
	}
	return 0, nil
}

func (m *MockAuthService) CleanupExpiredAPIKeys(ctx context.Context) (int64, error) {
	if m.CleanupExpiredAPIKeysFunc != nil {
		return m.CleanupExpiredAPIKeysFunc(ctx)
	}
	return 0, nil
}

// Mock JWT Service for testing
type MockJWTService struct {
	Config                          *config.JWTSettings
	GenerateAccessTokenFunc         func(userID int64, username, email string) (string, string, error)
	GenerateRefreshTokenFunc        func(userID int64, username, email string) (string, string, error)
	ValidateTokenFunc               func(tokenString string, expectedType string) (*auth.CustomClaims, error)
	ParseTokenWithoutValidationFunc func(tokenString string) (string, error)
	ExtractUserIDFromTokenFunc      func(tokenString string) (int64, error)
	RefreshTokensFunc               func(refreshToken, userID int64, username, email string) (string, string, string, string, error)
}

func (m *MockJWTService) GenerateAccessToken(userID int64, username, email string) (string, string, error) {
	if m.GenerateAccessTokenFunc != nil {
		return m.GenerateAccessTokenFunc(userID, username, email)
	}
	return "access_token", "jwt_id", nil
}

func (m *MockJWTService) GenerateRefreshToken(userID int64, username, email string) (string, string, error) {
	if m.GenerateRefreshTokenFunc != nil {
		return m.GenerateRefreshTokenFunc(userID, username, email)
	}
	return "refresh_token", "jwt_id", nil
}

func (m *MockJWTService) ValidateToken(tokenString string, expectedType string) (*auth.CustomClaims, error) {
	if m.ValidateTokenFunc != nil {
		return m.ValidateTokenFunc(tokenString, expectedType)
	}
	return &auth.CustomClaims{
		UserID:    1,
		Username:  "testuser",
		Email:     "test@example.com",
		TokenType: expectedType,
	}, nil
}

func (m *MockJWTService) ParseTokenWithoutValidation(tokenString string) (string, error) {
	if m.ParseTokenWithoutValidationFunc != nil {
		return m.ParseTokenWithoutValidationFunc(tokenString)
	}
	return "jwt_id", nil
}

func (m *MockJWTService) ExtractUserIDFromToken(tokenString string) (int64, error) {
	if m.ExtractUserIDFromTokenFunc != nil {
		return m.ExtractUserIDFromTokenFunc(tokenString)
	}
	return 1, nil
}

func (m *MockJWTService) RefreshTokens(refreshToken, userID int64, username, email string) (string, string, string, string, error) {
	if m.RefreshTokensFunc != nil {
		return m.RefreshTokensFunc(refreshToken, userID, username, email)
	}
	return "access_token", "access_jwt_id", "refresh_token", "refresh_jwt_id", nil
}

func (m *MockJWTService) GetConfig() *config.JWTSettings {
	return m.Config
}

// Helper function to set up the auth handler test
func setupAuthHandlerTest() (*AuthHandler, *MockAuthService, *MockJWTService) {
	mockAuthService := new(MockAuthService)
	mockJWTService := new(MockJWTService)
	mockJWTService.Config = &config.JWTSettings{
		Expiry:        15 * time.Minute,
		RefreshExpiry: 7 * 24 * time.Hour,
		Issuer:        "test-issuer",
		Secret:        "test-secret",
	}

	// Create the AuthHandler with the mock services
	handler := NewAuthHandler(mockAuthService, mockJWTService)

	return handler, mockAuthService, mockJWTService
}

// TestRegister tests the Register handler
func TestRegister(t *testing.T) {
	// Set up test cases
	testCases := []struct {
		name             string
		requestBody      map[string]interface{}
		mockSetup        func(*MockAuthService)
		expectedStatus   int
		validateResponse func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name: "Successful Registration",
			requestBody: map[string]interface{}{
				"username":         "testuser",
				"email":            "test@example.com",
				"password":         "password123",
				"confirm_password": "password123",
			},
			mockSetup: func(mock *MockAuthService) {
				mock.RegisterUserFunc = func(ctx context.Context, reg *models.UserRegistration) (*models.User, error) {
					return &models.User{
						ID:       1,
						Username: reg.Username,
						Email:    reg.Email,
					}, nil
				}
			},
			expectedStatus: http.StatusCreated,
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

				if id, _ := data["id"].(float64); id != 1 {
					t.Errorf("Expected user ID 1, got %v", id)
				}

				if username, _ := data["username"].(string); username != "testuser" {
					t.Errorf("Expected username 'testuser', got %s", username)
				}

				if email, _ := data["email"].(string); email != "test@example.com" {
					t.Errorf("Expected email 'test@example.com', got %s", email)
				}
			},
		},
		{
			name: "Password Mismatch",
			requestBody: map[string]interface{}{
				"username":         "testuser",
				"email":            "test@example.com",
				"password":         "password123",
				"confirm_password": "differentpassword",
			},
			mockSetup: func(mock *MockAuthService) {
				mock.RegisterUserFunc = func(ctx context.Context, reg *models.UserRegistration) (*models.User, error) {
					return nil, utils.NewValidationError("confirm_password", "Passwords do not match")
				}
			},
			expectedStatus: http.StatusBadRequest,
			validateResponse: func(t *testing.T, rec *httptest.ResponseRecorder) {
				var response map[string]interface{}
				err := json.Unmarshal(rec.Body.Bytes(), &response)
				if err != nil {
					t.Fatalf("Failed to unmarshal response: %v", err)
				}

				// Verify error response
				if success, _ := response["success"].(bool); success {
					t.Errorf("Expected success to be false")
				}

				errObj, ok := response["error"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected error object in response")
				}

				if code, _ := errObj["code"].(string); code != "validation_error" {
					t.Errorf("Expected error code 'validation_error', got %s", code)
				}
			},
		},
		{
			name: "Duplicate Username",
			requestBody: map[string]interface{}{
				"username":         "existinguser",
				"email":            "test@example.com",
				"password":         "password123",
				"confirm_password": "password123",
			},
			mockSetup: func(mock *MockAuthService) {
				mock.RegisterUserFunc = func(ctx context.Context, reg *models.UserRegistration) (*models.User, error) {
					return nil, utils.NewDuplicateError("User", "username", reg.Username)
				}
			},
			expectedStatus: http.StatusConflict,
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

				if code, _ := errObj["code"].(string); code != "duplicate_resource" {
					t.Errorf("Expected error code 'duplicate_resource', got %s", code)
				}
			},
		},
	}

	// Run test cases
	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Setup
			handler, mockAuthService, _ := setupAuthHandlerTest()
			if tc.mockSetup != nil {
				tc.mockSetup(mockAuthService)
			}

			// Create request
			requestBody, _ := json.Marshal(tc.requestBody)
			req, err := http.NewRequest("POST", "/api/auth/signup", bytes.NewBuffer(requestBody))
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}
			req.Header.Set("Content-Type", "application/json")

			// Create response recorder
			rec := httptest.NewRecorder()

			// Call handler
			handler.Register(rec, req)

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

// TestLogin tests the Login handler
func TestLogin(t *testing.T) {
	testCases := []struct {
		name             string
		requestBody      map[string]interface{}
		mockSetup        func(*MockAuthService, *MockJWTService)
		expectedStatus   int
		validateResponse func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name: "Successful Login",
			requestBody: map[string]interface{}{
				"username": "testuser",
				"password": "password123",
			},
			mockSetup: func(mockAuth *MockAuthService, mockJWT *MockJWTService) {
				mockAuth.AuthenticateUserFunc = func(ctx context.Context, creds *models.UserCredentials) (*models.User, string, string, error) {
					return &models.User{
						ID:       1,
						Username: "testuser",
						Email:    "test@example.com",
					}, "access_token_123", "refresh_token_456", nil
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

				if accessToken, _ := data["access_token"].(string); accessToken != "access_token_123" {
					t.Errorf("Expected access_token 'access_token_123', got %s", accessToken)
				}

				if tokenType, _ := data["token_type"].(string); tokenType != "Bearer" {
					t.Errorf("Expected token_type 'Bearer', got %s", tokenType)
				}

				// Check for user object
				user, ok := data["user"].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected user object in response")
				}

				if username, _ := user["username"].(string); username != "testuser" {
					t.Errorf("Expected username 'testuser', got %s", username)
				}

				// Verify refresh token cookie was set
				cookies := rec.Result().Cookies()
				var refreshTokenCookie *http.Cookie
				for _, cookie := range cookies {
					if cookie.Name == "refresh_token" {
						refreshTokenCookie = cookie
						break
					}
				}

				if refreshTokenCookie == nil {
					t.Errorf("Refresh token cookie not set")
				} else if refreshTokenCookie.Value != "refresh_token_456" {
					t.Errorf("Expected refresh token value 'refresh_token_456', got %s", refreshTokenCookie.Value)
				}
			},
		},
		{
			name: "Invalid Credentials",
			requestBody: map[string]interface{}{
				"username": "testuser",
				"password": "wrongpassword",
			},
			mockSetup: func(mockAuth *MockAuthService, mockJWT *MockJWTService) {
				mockAuth.AuthenticateUserFunc = func(ctx context.Context, creds *models.UserCredentials) (*models.User, string, string, error) {
					return nil, "", "", utils.NewInvalidCredentialsError()
				}
			},
			expectedStatus: http.StatusUnauthorized,
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

				if code, _ := errObj["code"].(string); code != "invalid_credentials" {
					t.Errorf("Expected error code 'invalid_credentials', got %s", code)
				}
			},
		},
		{
			name: "Missing Required Fields",
			requestBody: map[string]interface{}{
				"username": "",
				"password": "",
			},
			mockSetup: func(mockAuth *MockAuthService, mockJWT *MockJWTService) {
				mockAuth.AuthenticateUserFunc = func(ctx context.Context, creds *models.UserCredentials) (*models.User, string, string, error) {
					return nil, "", "", utils.NewValidationError("credentials", "Username or email is required")
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

				if code, _ := errObj["code"].(string); code != "validation_error" {
					t.Errorf("Expected error code 'validation_error', got %s", code)
				}
			},
		},
	}

	// Run test cases
	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Setup
			handler, mockAuthService, mockJWTService := setupAuthHandlerTest()
			if tc.mockSetup != nil {
				tc.mockSetup(mockAuthService, mockJWTService)
			}

			// Create request
			requestBody, _ := json.Marshal(tc.requestBody)
			req, err := http.NewRequest("POST", "/api/auth/login", bytes.NewBuffer(requestBody))
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}
			req.Header.Set("Content-Type", "application/json")

			// Create response recorder
			rec := httptest.NewRecorder()

			// Call handler
			handler.Login(rec, req)

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

// TestRefreshToken tests the RefreshToken handler
func TestRefreshToken(t *testing.T) {
	testCases := []struct {
		name             string
		setupCookie      func(*http.Request)
		mockSetup        func(*MockAuthService)
		expectedStatus   int
		validateResponse func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name: "Successful Token Refresh",
			setupCookie: func(req *http.Request) {
				cookie := &http.Cookie{
					Name:  "refresh_token",
					Value: "valid_refresh_token",
				}
				req.AddCookie(cookie)
			},
			mockSetup: func(mock *MockAuthService) {
				mock.RefreshTokensFunc = func(ctx context.Context, refreshToken string) (string, string, error) {
					return "new_access_token", "new_refresh_token", nil
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

				if accessToken, _ := data["access_token"].(string); accessToken != "new_access_token" {
					t.Errorf("Expected access_token 'new_access_token', got %s", accessToken)
				}

				// Check refresh token cookie
				cookies := rec.Result().Cookies()
				var refreshTokenCookie *http.Cookie
				for _, cookie := range cookies {
					if cookie.Name == "refresh_token" {
						refreshTokenCookie = cookie
						break
					}
				}

				if refreshTokenCookie == nil {
					t.Errorf("Refresh token cookie not set")
				} else if refreshTokenCookie.Value != "new_refresh_token" {
					t.Errorf("Expected refresh token value 'new_refresh_token', got %s", refreshTokenCookie.Value)
				}
			},
		},
		{
			name: "Missing Refresh Token",
			setupCookie: func(req *http.Request) {
				// No cookie set
			},
			mockSetup:      func(mock *MockAuthService) {},
			expectedStatus: http.StatusUnauthorized,
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

				if message, _ := errObj["message"].(string); message != "Refresh token not found" {
					t.Errorf("Expected error message 'Refresh token not found', got %s", message)
				}
			},
		},
		{
			name: "Invalid Refresh Token",
			setupCookie: func(req *http.Request) {
				cookie := &http.Cookie{
					Name:  "refresh_token",
					Value: "invalid_refresh_token",
				}
				req.AddCookie(cookie)
			},
			mockSetup: func(mock *MockAuthService) {
				mock.RefreshTokensFunc = func(ctx context.Context, refreshToken string) (string, string, error) {
					return "", "", utils.NewInvalidTokenError()
				}
			},
			expectedStatus: http.StatusUnauthorized,
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

				if code, _ := errObj["code"].(string); code != "token_invalid" {
					t.Errorf("Expected error code 'token_invalid', got %s", code)
				}
			},
		},
	}

	// Run test cases
	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Setup
			handler, mockAuthService, _ := setupAuthHandlerTest()
			if tc.mockSetup != nil {
				tc.mockSetup(mockAuthService)
			}

			// Create request
			req, err := http.NewRequest("POST", "/api/auth/refresh", nil)
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}

			// Setup cookie if needed
			if tc.setupCookie != nil {
				tc.setupCookie(req)
			}

			// Create response recorder
			rec := httptest.NewRecorder()

			// Call handler
			handler.RefreshToken(rec, req)

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

// TestLogout tests the Logout handler
func TestLogout(t *testing.T) {
	testCases := []struct {
		name           string
		setupCookie    func(*http.Request)
		mockSetup      func(*MockAuthService)
		expectedStatus int
		validateCookie func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name: "Successful Logout",
			setupCookie: func(req *http.Request) {
				cookie := &http.Cookie{
					Name:  "refresh_token",
					Value: "valid_refresh_token",
				}
				req.AddCookie(cookie)
			},
			mockSetup: func(mock *MockAuthService) {
				mock.LogoutFunc = func(ctx context.Context, refreshToken string) error {
					return nil
				}
			},
			expectedStatus: http.StatusOK,
			validateCookie: func(t *testing.T, rec *httptest.ResponseRecorder) {
				cookies := rec.Result().Cookies()
				var refreshTokenCookie *http.Cookie
				for _, cookie := range cookies {
					if cookie.Name == "refresh_token" {
						refreshTokenCookie = cookie
						break
					}
				}

				if refreshTokenCookie == nil {
					t.Errorf("Refresh token cookie not cleared")
				} else {
					// Check if cookie was cleared (MaxAge < 0)
					if refreshTokenCookie.MaxAge >= 0 {
						t.Errorf("Expected refresh token cookie MaxAge < 0, got %d", refreshTokenCookie.MaxAge)
					}

					// Check if cookie was expired
					if !refreshTokenCookie.Expires.Before(time.Now()) {
						t.Errorf("Expected refresh token cookie to be expired")
					}
				}
			},
		},
		{
			name: "Logout Without Cookie",
			setupCookie: func(req *http.Request) {
				// No cookie set
			},
			mockSetup: func(mock *MockAuthService) {
				// Service should not be called
			},
			expectedStatus: http.StatusOK,
			validateCookie: func(t *testing.T, rec *httptest.ResponseRecorder) {
				cookies := rec.Result().Cookies()
				var refreshTokenCookie *http.Cookie
				for _, cookie := range cookies {
					if cookie.Name == "refresh_token" {
						refreshTokenCookie = cookie
						break
					}
				}

				if refreshTokenCookie == nil {
					t.Errorf("Refresh token cookie not set")
				} else {
					// Check if cookie was cleared (MaxAge < 0)
					if refreshTokenCookie.MaxAge >= 0 {
						t.Errorf("Expected refresh token cookie MaxAge < 0, got %d", refreshTokenCookie.MaxAge)
					}
				}
			},
		},
	}

	// Run test cases
	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Setup
			handler, mockAuthService, _ := setupAuthHandlerTest()
			if tc.mockSetup != nil {
				tc.mockSetup(mockAuthService)
			}

			// Create request
			req, err := http.NewRequest("POST", "/api/auth/logout", nil)
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}

			// Setup cookie if needed
			if tc.setupCookie != nil {
				tc.setupCookie(req)
			}

			// Create response recorder
			rec := httptest.NewRecorder()

			// Call handler
			handler.Logout(rec, req)

			// Check status code
			if rec.Code != tc.expectedStatus {
				t.Errorf("Expected status code %d, got %d", tc.expectedStatus, rec.Code)
			}

			// Validate cookie
			if tc.validateCookie != nil {
				tc.validateCookie(t, rec)
			}
		})
	}
}

// TestCreateAPIKey tests the CreateAPIKey handler
func TestCreateAPIKey(t *testing.T) {
	testCases := []struct {
		name             string
		requestBody      map[string]interface{}
		setupRequest     func(*http.Request)
		mockSetup        func(*MockAuthService)
		expectedStatus   int
		validateResponse func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name: "Successfully Create API Key",
			requestBody: map[string]interface{}{
				"name":     "Test API Key",
				"duration": "30d",
			},
			setupRequest: func(req *http.Request) {
				// Set authenticated user in context
				ctx := context.WithValue(req.Context(), auth.UserIDContextKey, int64(1))
				ctx = context.WithValue(ctx, auth.UsernameContextKey, "testuser")
				ctx = context.WithValue(ctx, auth.EmailContextKey, "test@example.com")
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockAuthService) {
				mock.CreateAPIKeyFunc = func(ctx context.Context, userID int64, name string, duration time.Duration) (string, *models.APIKey, error) {
					return "test-api-key-raw", &models.APIKey{
						ID:        "key123",
						UserID:    userID,
						Name:      name,
						ExpiresAt: time.Now().Add(30 * 24 * time.Hour),
						CreatedAt: time.Now(),
					}, nil
				}
			},
			expectedStatus: http.StatusCreated,
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

				if key, _ := data["key"].(string); key != "test-api-key-raw" {
					t.Errorf("Expected API key 'test-api-key-raw', got %s", key)
				}

				if name, _ := data["name"].(string); name != "Test API Key" {
					t.Errorf("Expected key name 'Test API Key', got %s", name)
				}
			},
		},
		{
			name: "Unauthenticated Request",
			requestBody: map[string]interface{}{
				"name":     "Test API Key",
				"duration": "30d",
			},
			setupRequest: func(req *http.Request) {
				// No auth context
			},
			mockSetup: func(mock *MockAuthService) {
				// Service should not be called
			},
			expectedStatus: http.StatusUnauthorized,
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

				if code, _ := errObj["code"].(string); code != "unauthorized" {
					t.Errorf("Expected error code 'unauthorized', got %s", code)
				}
			},
		},
		{
			name: "Invalid Duration",
			requestBody: map[string]interface{}{
				"name":     "Test API Key",
				"duration": "invalid",
			},
			setupRequest: func(req *http.Request) {
				// Set authenticated user in context
				ctx := context.WithValue(req.Context(), auth.UserIDContextKey, int64(1))
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockAuthService) {
				mock.CreateAPIKeyFunc = func(ctx context.Context, userID int64, name string, duration time.Duration) (string, *models.APIKey, error) {
					return "", nil, utils.NewValidationError("duration", "Invalid duration. Must be one of: 30d, 90d, 180d, 365d")
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

				if code, _ := errObj["code"].(string); code != "validation_error" {
					t.Errorf("Expected error code 'validation_error', got %s", code)
				}
			},
		},
	}

	// Run test cases
	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Setup
			handler, mockAuthService, _ := setupAuthHandlerTest()
			if tc.mockSetup != nil {
				tc.mockSetup(mockAuthService)
			}

			// Create request
			requestBody, _ := json.Marshal(tc.requestBody)
			req, err := http.NewRequest("POST", "/api/auth/keys", bytes.NewBuffer(requestBody))
			if err != nil {
				t.Fatalf("Failed to create request: %v", err)
			}
			req.Header.Set("Content-Type", "application/json")

			// Setup request context if needed
			if tc.setupRequest != nil {
				tc.setupRequest(req)
			}

			// Create response recorder
			rec := httptest.NewRecorder()

			// Call handler
			handler.CreateAPIKey(rec, req)

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

// TestListAPIKeys tests the ListAPIKeys handler
func TestListAPIKeys(t *testing.T) {
	testCases := []struct {
		name             string
		setupRequest     func(*http.Request)
		mockSetup        func(*MockAuthService)
		expectedStatus   int
		validateResponse func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name: "Successfully List API Keys",
			setupRequest: func(req *http.Request) {
				// Set authenticated user in context
				ctx := context.WithValue(req.Context(), auth.UserIDContextKey, int64(1))
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockAuthService) {
				mock.ListAPIKeysFunc = func(ctx context.Context, userID int64) ([]*models.APIKey, error) {
					now := time.Now()
					return []*models.APIKey{
						{
							ID:        "key1",
							UserID:    userID,
							Name:      "API Key 1",
							ExpiresAt: now.Add(30 * 24 * time.Hour),
							CreatedAt: now.Add(-24 * time.Hour),
						},
						{
							ID:        "key2",
							UserID:    userID,
							Name:      "API Key 2",
							ExpiresAt: now.Add(90 * 24 * time.Hour),
							CreatedAt: now,
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

				if len(data) != 2 {
					t.Errorf("Expected 2 API keys, got %d", len(data))
				}

				// Check first key
				firstKey, ok := data[0].(map[string]interface{})
				if !ok {
					t.Fatalf("Expected first key to be an object")
				}

				if id, _ := firstKey["id"].(string); id != "key1" {
					t.Errorf("Expected first key ID 'key1', got %s", id)
				}

				if name, _ := firstKey["name"].(string); name != "API Key 1" {
					t.Errorf("Expected first key name 'API Key 1', got %s", name)
				}
			},
		},
		{
			name: "Unauthenticated Request",
			setupRequest: func(req *http.Request) {
				// No auth context
			},
			mockSetup: func(mock *MockAuthService) {
				// Service should not be called
			},
			expectedStatus: http.StatusUnauthorized,
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

				if code, _ := errObj["code"].(string); code != "unauthorized" {
					t.Errorf("Expected error code 'unauthorized', got %s", code)
				}
			},
		},
		{
			name: "Service Error",
			setupRequest: func(req *http.Request) {
				// Set authenticated user in context
				ctx := context.WithValue(req.Context(), auth.UserIDContextKey, int64(1))
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockAuthService) {
				mock.ListAPIKeysFunc = func(ctx context.Context, userID int64) ([]*models.APIKey, error) {
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
			handler, mockAuthService, _ := setupAuthHandlerTest()
			if tc.mockSetup != nil {
				tc.mockSetup(mockAuthService)
			}

			// Create request
			req, err := http.NewRequest("GET", "/api/auth/keys", nil)
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
			handler.ListAPIKeys(rec, req)

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

// TestDeleteAPIKey tests the DeleteAPIKey handler
func TestDeleteAPIKey(t *testing.T) {
	testCases := []struct {
		name             string
		keyID            string
		setupRequest     func(*http.Request)
		mockSetup        func(*MockAuthService)
		expectedStatus   int
		validateResponse func(*testing.T, *httptest.ResponseRecorder)
	}{
		{
			name:  "Successfully Delete API Key",
			keyID: "key123",
			setupRequest: func(req *http.Request) {
				// Set authenticated user in context
				ctx := context.WithValue(req.Context(), auth.UserIDContextKey, int64(1))
				*req = *req.WithContext(ctx)

				// Setup chi URL parameter
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("keyID", "key123")
				ctx = context.WithValue(ctx, chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockAuthService) {
				mock.DeleteAPIKeyFunc = func(ctx context.Context, userID int64, keyID string) error {
					if keyID != "key123" {
						return utils.NewNotFoundError("APIKey", keyID)
					}
					return nil
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

				message, ok := data["message"].(string)
				if !ok || message != "API key successfully revoked" {
					t.Errorf("Expected message 'API key successfully revoked', got %v", message)
				}
			},
		},
		{
			name:  "Unauthenticated Request",
			keyID: "key123",
			setupRequest: func(req *http.Request) {
				// No auth context

				// Setup chi URL parameter
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("keyID", "key123")
				ctx := context.WithValue(req.Context(), chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockAuthService) {
				// Service should not be called
			},
			expectedStatus: http.StatusUnauthorized,
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

				if code, _ := errObj["code"].(string); code != "unauthorized" {
					t.Errorf("Expected error code 'unauthorized', got %s", code)
				}
			},
		},
		{
			name:  "Missing Key ID",
			keyID: "",
			setupRequest: func(req *http.Request) {
				// Set authenticated user in context
				ctx := context.WithValue(req.Context(), auth.UserIDContextKey, int64(1))
				*req = *req.WithContext(ctx)

				// Setup empty chi URL parameter
				chiCtx := chi.NewRouteContext()
				ctx = context.WithValue(ctx, chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockAuthService) {
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

				if message, _ := errObj["message"].(string); message != "key_id parameter is required" {
					t.Errorf("Expected error message 'key_id parameter is required', got %s", message)
				}
			},
		},
		{
			name:  "Key Not Found",
			keyID: "nonexistent",
			setupRequest: func(req *http.Request) {
				// Set authenticated user in context
				ctx := context.WithValue(req.Context(), auth.UserIDContextKey, int64(1))
				*req = *req.WithContext(ctx)

				// Setup chi URL parameter
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("keyID", "nonexistent")
				ctx = context.WithValue(ctx, chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockAuthService) {
				mock.DeleteAPIKeyFunc = func(ctx context.Context, userID int64, keyID string) error {
					return utils.NewNotFoundError("APIKey", keyID)
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
			name:  "Forbidden - Key Belongs to Another User",
			keyID: "key123",
			setupRequest: func(req *http.Request) {
				// Set authenticated user in context
				ctx := context.WithValue(req.Context(), auth.UserIDContextKey, int64(1))
				*req = *req.WithContext(ctx)

				// Setup chi URL parameter
				chiCtx := chi.NewRouteContext()
				chiCtx.URLParams.Add("keyID", "key123")
				ctx = context.WithValue(ctx, chi.RouteCtxKey, chiCtx)
				*req = *req.WithContext(ctx)
			},
			mockSetup: func(mock *MockAuthService) {
				mock.DeleteAPIKeyFunc = func(ctx context.Context, userID int64, keyID string) error {
					return utils.NewForbiddenError("You do not have permission to delete this API key")
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
	}

	// Run test cases
	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Setup
			handler, mockAuthService, _ := setupAuthHandlerTest()
			if tc.mockSetup != nil {
				tc.mockSetup(mockAuthService)
			}

			// Create request
			req, err := http.NewRequest("DELETE", "/api/auth/keys/"+tc.keyID, nil)
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
			handler.DeleteAPIKey(rec, req)

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

// Additional tests for LogoutAll, VerifyToken, and ValidateAPIKey would follow a similar pattern
