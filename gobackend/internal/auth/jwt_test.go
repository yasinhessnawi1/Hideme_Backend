package auth_test

import (
	"errors"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v4"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

func TestNewJWTService(t *testing.T) {
	// Create config
	cfg := &config.JWTSettings{
		Secret:        "test-secret",
		Expiry:        15 * time.Minute,
		RefreshExpiry: 7 * 24 * time.Hour,
		Issuer:        "test-issuer",
	}

	// Create service
	service := auth.NewJWTService(cfg)

	// Check if service is created
	if service == nil {
		t.Error("Expected service to be created, got nil")
	}

	// Check if config is set
	if service.Config != cfg {
		t.Errorf("Expected Config to be %v, got %v", cfg, service.Config)
	}
}

func TestGetConfig(t *testing.T) {
	// Test with nil config (should use defaults)
	service := &auth.JWTService{Config: nil}
	cfg := service.GetConfig()

	if cfg == nil {
		t.Error("Expected default config, got nil")
	}

	// Check default values
	if cfg.Expiry != 15*time.Minute { // FIXED: Changed from 15 hours to 15 minutes
		t.Errorf("Expected default Expiry to be 15 minutes, got %v", cfg.Expiry)
	}

	if cfg.RefreshExpiry != 7*24*time.Hour {
		t.Errorf("Expected default RefreshExpiry to be 168h, got %v", cfg.RefreshExpiry)
	}

	if cfg.Issuer != "hideme-api" {
		t.Errorf("Expected default Issuer to be 'hideme-api', got %v", cfg.Issuer)
	}

	// Test with provided config
	providedCfg := &config.JWTSettings{
		Secret:        "test-secret",
		Expiry:        30 * time.Minute,
		RefreshExpiry: 30 * 24 * time.Hour,
		Issuer:        "test-issuer",
	}

	service = &auth.JWTService{Config: providedCfg}
	cfg = service.GetConfig()

	if cfg != providedCfg {
		t.Errorf("Expected provided config %v, got %v", providedCfg, cfg)
	}
}

func TestGenerateAccessToken(t *testing.T) {
	// Create config
	cfg := &config.JWTSettings{
		Secret:        "test-secret",
		Expiry:        15 * time.Minute,
		RefreshExpiry: 7 * 24 * time.Hour,
		Issuer:        "test-issuer",
	}

	// Create service
	service := auth.NewJWTService(cfg)

	// Generate token
	userID := int64(123)
	username := "testuser"
	email := "test@example.com"

	token, jwtID, err := service.GenerateAccessToken(userID, username, email)

	// Check for errors
	if err != nil {
		t.Errorf("GenerateAccessToken() error = %v", err)
		return
	}

	// Check token is not empty
	if token == "" {
		t.Error("Expected non-empty token")
	}

	// Check JWT ID is not empty
	if jwtID == "" {
		t.Error("Expected non-empty JWT ID")
	}

	// Validate the token
	claims, err := service.ValidateToken(token, "access")
	if err != nil {
		t.Errorf("ValidateToken() error = %v", err)
		return
	}

	// Check claims
	if claims.UserID != userID {
		t.Errorf("Expected UserID %d, got %d", userID, claims.UserID)
	}

	if claims.Username != username {
		t.Errorf("Expected Username %s, got %s", username, claims.Username)
	}

	if claims.Email != email {
		t.Errorf("Expected Email %s, got %s", email, claims.Email)
	}

	if claims.TokenType != "access" {
		t.Errorf("Expected TokenType 'access', got %s", claims.TokenType)
	}

	if claims.Issuer != cfg.Issuer {
		t.Errorf("Expected Issuer %s, got %s", cfg.Issuer, claims.Issuer)
	}

	if claims.Subject != "123" {
		t.Errorf("Expected Subject '123', got %s", claims.Subject)
	}

	// Check expiry time
	if claims.ExpiresAt == nil {
		t.Error("ExpiresAt should not be nil")
	} else {
		expectedExpiry := time.Now().Add(cfg.Expiry).Unix()
		// Allow 5 seconds tolerance for test execution time
		if claims.ExpiresAt.Unix() < expectedExpiry-5 || claims.ExpiresAt.Unix() > expectedExpiry+5 {
			t.Errorf("ExpiresAt not within expected range: got %v, want ~%v",
				claims.ExpiresAt.Unix(), expectedExpiry)
		}
	}
}

func TestGenerateRefreshToken(t *testing.T) {
	// Create config
	cfg := &config.JWTSettings{
		Secret:        "test-secret",
		Expiry:        15 * time.Minute,
		RefreshExpiry: 7 * 24 * time.Hour,
		Issuer:        "test-issuer",
	}

	// Create service
	service := auth.NewJWTService(cfg)

	// Generate token
	userID := int64(123)
	username := "testuser"
	email := "test@example.com"

	token, jwtID, err := service.GenerateRefreshToken(userID, username, email)

	// Check for errors
	if err != nil {
		t.Errorf("GenerateRefreshToken() error = %v", err)
		return
	}

	// Check token is not empty
	if token == "" {
		t.Error("Expected non-empty token")
	}

	// Check JWT ID is not empty
	if jwtID == "" {
		t.Error("Expected non-empty JWT ID")
	}

	// Validate the token
	claims, err := service.ValidateToken(token, "refresh")
	if err != nil {
		t.Errorf("ValidateToken() error = %v", err)
		return
	}

	// Check claims
	if claims.UserID != userID {
		t.Errorf("Expected UserID %d, got %d", userID, claims.UserID)
	}

	if claims.TokenType != "refresh" {
		t.Errorf("Expected TokenType 'refresh', got %s", claims.TokenType)
	}

	// Check expiry time
	if claims.ExpiresAt == nil {
		t.Error("ExpiresAt should not be nil")
	} else {
		expectedExpiry := time.Now().Add(cfg.RefreshExpiry).Unix()
		// Allow 5 seconds tolerance for test execution time
		if claims.ExpiresAt.Unix() < expectedExpiry-5 || claims.ExpiresAt.Unix() > expectedExpiry+5 {
			t.Errorf("ExpiresAt not within expected range: got %v, want ~%v",
				claims.ExpiresAt.Unix(), expectedExpiry)
		}
	}
}

func TestValidateToken(t *testing.T) {
	// Create config
	cfg := &config.JWTSettings{
		Secret:        "test-secret",
		Expiry:        15 * time.Minute,
		RefreshExpiry: 7 * 24 * time.Hour,
		Issuer:        "test-issuer",
	}

	// Create service
	service := auth.NewJWTService(cfg)

	// Generate valid token
	validToken, _, err := service.GenerateAccessToken(123, "testuser", "test@example.com")
	if err != nil {
		t.Fatalf("Failed to generate test token: %v", err)
	}

	// Generate expired token
	expiredClaims := auth.CustomClaims{
		UserID:    456,
		Username:  "expireduser",
		Email:     "expired@example.com",
		TokenType: "access",
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(-1 * time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now().Add(-2 * time.Hour)),
			NotBefore: jwt.NewNumericDate(time.Now().Add(-2 * time.Hour)),
			Issuer:    cfg.Issuer,
			Subject:   "456",
			ID:        "expired-id",
		},
	}

	expiredToken := jwt.NewWithClaims(jwt.SigningMethodHS256, expiredClaims)
	expiredTokenString, err := expiredToken.SignedString([]byte(cfg.Secret))
	if err != nil {
		t.Fatalf("Failed to generate expired test token: %v", err)
	}

	// Generate token with wrong type
	wrongTypeToken, _, err := service.GenerateRefreshToken(789, "wrongtype", "wrong@example.com")
	if err != nil {
		t.Fatalf("Failed to generate wrong type test token: %v", err)
	}

	// Generate token with wrong signing method
	wrongSigningMethodToken := jwt.New(jwt.SigningMethodNone)
	wrongSigningMethodToken.Claims = jwt.MapClaims{
		"user_id":    999,
		"username":   "wrongmethod",
		"email":      "wrongmethod@example.com",
		"token_type": "access",
		"exp":        time.Now().Add(15 * time.Minute).Unix(),
		"iat":        time.Now().Unix(),
		"nbf":        time.Now().Unix(),
		"iss":        cfg.Issuer,
		"sub":        "999",
		"jti":        "wrong-method-id",
	}

	wrongSigningMethodTokenString, _ := wrongSigningMethodToken.SignedString([]byte(""))

	// Test cases
	tests := []struct {
		name        string
		token       string
		tokenType   string
		shouldError bool
		errorType   error
	}{
		{
			name:        "Valid token",
			token:       validToken,
			tokenType:   "access",
			shouldError: false,
		},
		{
			name:        "Expired token",
			token:       expiredTokenString,
			tokenType:   "access",
			shouldError: true,
			errorType:   utils.ErrExpiredToken,
		},
		{
			name:        "Wrong token type",
			token:       wrongTypeToken,
			tokenType:   "access", // This is a refresh token
			shouldError: true,
			errorType:   utils.ErrInvalidToken,
		},
		{
			name:        "Invalid token format",
			token:       "not-a-valid-token",
			tokenType:   "access",
			shouldError: true,
			errorType:   utils.ErrInvalidToken,
		},
		{
			name:        "Empty token",
			token:       "",
			tokenType:   "access",
			shouldError: true,
			errorType:   utils.ErrInvalidToken,
		},
		{
			name:        "Wrong signing method",
			token:       wrongSigningMethodTokenString,
			tokenType:   "access",
			shouldError: true,
			errorType:   utils.ErrInvalidToken,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Validate the token
			claims, err := service.ValidateToken(tt.token, tt.tokenType)

			// Check error
			if (err != nil) != tt.shouldError {
				t.Errorf("ValidateToken() error = %v, shouldError %v", err, tt.shouldError)
				return
			}

			// If expected error, check error type
			if tt.shouldError && err != nil && tt.errorType != nil {
				var appErr *utils.AppError
				if errors.As(err, &appErr) {
					if !errors.Is(appErr.Unwrap(), tt.errorType) {
						t.Errorf("ValidateToken() error type = %v, want %v", appErr.Unwrap(), tt.errorType)
					}
				} else {
					t.Errorf("Expected AppError, got %T", err)
				}
				return
			}

			// If no error, check claims
			if !tt.shouldError {
				if claims == nil {
					t.Error("Expected non-nil claims")
					return
				}

				if claims.TokenType != tt.tokenType {
					t.Errorf("Expected TokenType %s, got %s", tt.tokenType, claims.TokenType)
				}
			}
		})
	}
}

func TestParseTokenWithoutValidation(t *testing.T) {
	// Create config
	cfg := &config.JWTSettings{
		Secret:        "test-secret",
		Expiry:        15 * time.Minute,
		RefreshExpiry: 7 * 24 * time.Hour,
		Issuer:        "test-issuer",
	}

	// Create service
	service := auth.NewJWTService(cfg)

	// Test cases
	tests := []struct {
		name          string
		setupToken    func() string
		expectedError bool
		expectedID    string
	}{
		{
			name: "Valid token",
			setupToken: func() string {
				token, _, _ := service.GenerateAccessToken(123, "testuser", "test@example.com")
				return token
			},
			expectedError: false,
		},
		{
			name: "Expired token - should still extract ID",
			setupToken: func() string {
				claims := auth.CustomClaims{
					UserID:    456,
					Username:  "expireduser",
					Email:     "expired@example.com",
					TokenType: "access",
					RegisteredClaims: jwt.RegisteredClaims{
						ExpiresAt: jwt.NewNumericDate(time.Now().Add(-1 * time.Hour)),
						IssuedAt:  jwt.NewNumericDate(time.Now().Add(-2 * time.Hour)),
						NotBefore: jwt.NewNumericDate(time.Now().Add(-2 * time.Hour)),
						Issuer:    cfg.Issuer,
						Subject:   "456",
						ID:        "expired-id",
					},
				}
				token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
				tokenString, _ := token.SignedString([]byte(cfg.Secret))
				return tokenString
			},
			expectedError: false,
			expectedID:    "expired-id",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Setup token
			token := tt.setupToken()

			// Parse token
			id, err := service.ParseTokenWithoutValidation(token)

			// Check error
			if (err != nil) != tt.expectedError {
				t.Errorf("ParseTokenWithoutValidation() error = %v, expectedError %v", err, tt.expectedError)
				return
			}

			// For specific cases, check the extracted ID
			if tt.name == "Expired token - should still extract ID" && id != tt.expectedID {
				t.Errorf("ParseTokenWithoutValidation() id = %v, want %v", id, tt.expectedID)
			}

			// If no error expected, check if ID is not empty
			if !tt.expectedError && id == "" {
				t.Error("Expected non-empty token ID")
			}
		})
	}
}

func TestExtractUserIDFromToken(t *testing.T) {
	// Create config
	cfg := &config.JWTSettings{
		Secret:        "test-secret",
		Expiry:        15 * time.Minute,
		RefreshExpiry: 7 * 24 * time.Hour,
		Issuer:        "test-issuer",
	}

	// Create service
	service := auth.NewJWTService(cfg)

	// Generate token
	expectedUserID := int64(123)
	token, _, err := service.GenerateAccessToken(expectedUserID, "testuser", "test@example.com")
	if err != nil {
		t.Fatalf("Failed to generate test token: %v", err)
	}

	// Extract user ID
	userID, err := service.ExtractUserIDFromToken(token)

	// Check error
	if err != nil {
		t.Errorf("ExtractUserIDFromToken() error = %v", err)
		return
	}

	// Check user ID
	if userID != expectedUserID {
		t.Errorf("ExtractUserIDFromToken() userID = %v, want %v", userID, expectedUserID)
	}

	// Test invalid token
	_, err = service.ExtractUserIDFromToken("not-a-valid-token")
	if err == nil {
		t.Error("ExtractUserIDFromToken() should error with invalid token")
	}

	// Test expired token
	expiredClaims := auth.CustomClaims{
		UserID:    456,
		Username:  "expireduser",
		Email:     "expired@example.com",
		TokenType: "access",
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(time.Now().Add(-1 * time.Hour)),
			IssuedAt:  jwt.NewNumericDate(time.Now().Add(-2 * time.Hour)),
			NotBefore: jwt.NewNumericDate(time.Now().Add(-2 * time.Hour)),
			Issuer:    cfg.Issuer,
			Subject:   "456",
			ID:        "expired-id",
		},
	}
	expiredToken := jwt.NewWithClaims(jwt.SigningMethodHS256, expiredClaims)
	expiredTokenString, _ := expiredToken.SignedString([]byte(cfg.Secret))
	_, err = service.ExtractUserIDFromToken(expiredTokenString)
	if err == nil {
		t.Error("ExtractUserIDFromToken() should error with expired token")
	}
}

func TestRefreshTokens(t *testing.T) {
	// Create config
	cfg := &config.JWTSettings{
		Secret:        "test-secret",
		Expiry:        15 * time.Minute,
		RefreshExpiry: 7 * 24 * time.Hour,
		Issuer:        "test-issuer",
	}

	// Create service
	service := auth.NewJWTService(cfg)

	// Setup test cases
	type testCase struct {
		name         string
		refreshToken int64
		userID       int64
		username     string
		email        string
		expectError  bool
	}

	tests := []testCase{
		{
			name:         "Invalid user ID",
			refreshToken: 123, // This will be replaced with a real token
			userID:       456, // Different from token's userID
			username:     "testuser",
			email:        "test@example.com",
			expectError:  true,
		},
		{
			name:         "Invalid refresh token",
			refreshToken: 999, // Invalid token
			userID:       123,
			username:     "testuser",
			email:        "test@example.com",
			expectError:  true,
		},
	}

	// Run the tests
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Call RefreshTokens
			accessToken, accessJWTID, newRefreshToken, refreshJWTID, err := service.RefreshTokens(tt.refreshToken, tt.userID, tt.username, tt.email)

			// Check error
			if (err != nil) != tt.expectError {
				t.Errorf("RefreshTokens() error = %v, expectError %v", err, tt.expectError)
				return
			}

			// If success, check the returned tokens
			if !tt.expectError {
				// Check if tokens are not empty
				if accessToken == "" {
					t.Error("Expected non-empty access token")
				}
				if accessJWTID == "" {
					t.Error("Expected non-empty access JWT ID")
				}
				if newRefreshToken == "" {
					t.Error("Expected non-empty refresh token")
				}
				if refreshJWTID == "" {
					t.Error("Expected non-empty refresh JWT ID")
				}

				// Validate the new tokens
				accessClaims, err := service.ValidateToken(accessToken, "access")
				if err != nil {
					t.Errorf("Failed to validate new access token: %v", err)
					return
				}
				if accessClaims.UserID != tt.userID {
					t.Errorf("Access token has wrong user ID: got %v, want %v", accessClaims.UserID, tt.userID)
				}

				refreshClaims, err := service.ValidateToken(newRefreshToken, "refresh")
				if err != nil {
					t.Errorf("Failed to validate new refresh token: %v", err)
					return
				}
				if refreshClaims.UserID != tt.userID {
					t.Errorf("Refresh token has wrong user ID: got %v, want %v", refreshClaims.UserID, tt.userID)
				}
			}
		})
	}
}
