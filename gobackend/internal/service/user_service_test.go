package service

import (
	"context"
	"testing"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestNewUserService(t *testing.T) {
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	passwordCfg := auth.DefaultPasswordConfig()

	service := NewUserService(userRepo, sessionRepo, apiKeyRepo, passwordCfg)

	if service == nil {
		t.Error("Expected non-nil service")
	}
}

func TestUserService_GetUserByID(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	passwordCfg := auth.DefaultPasswordConfig()

	service := NewUserService(userRepo, sessionRepo, apiKeyRepo, passwordCfg)

	// Create a test user
	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed-password",
		Salt:         "salt-value",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Get user by ID
	retrievedUser, err := service.GetUserByID(context.Background(), user.ID)

	// Check results
	if err != nil {
		t.Errorf("GetUserByID() error = %v", err)
	}

	if retrievedUser == nil {
		t.Fatal("Expected non-nil user")
	}

	if retrievedUser.ID != user.ID {
		t.Errorf("Expected ID = %d, got %d", user.ID, retrievedUser.ID)
	}

	// Check that sensitive information is sanitized
	if retrievedUser.PasswordHash != "" {
		t.Error("Expected empty PasswordHash in sanitized user")
	}

	if retrievedUser.Salt != "" {
		t.Error("Expected empty Salt in sanitized user")
	}

	// Test with non-existent user
	_, err = service.GetUserByID(context.Background(), 999)

	// Check that we get a not found error
	if err == nil {
		t.Error("Expected error for non-existent user")
	}
}

func TestUserService_DeleteUser(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	passwordCfg := auth.DefaultPasswordConfig()

	service := NewUserService(userRepo, sessionRepo, apiKeyRepo, passwordCfg)

	// Create a test user
	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed-password",
		Salt:         "salt-value",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Create a session
	session := &models.Session{
		ID:        "testsession",
		UserID:    user.ID,
		JWTID:     "testjwt",
		ExpiresAt: time.Now().Add(24 * time.Hour),
		CreatedAt: time.Now(),
	}

	err = sessionRepo.Create(context.Background(), session)
	if err != nil {
		t.Fatalf("Failed to create session: %v", err)
	}

	// Create an API key
	apiKey := &models.APIKey{
		ID:         "testkey",
		UserID:     user.ID,
		APIKeyHash: "testhash",
		Name:       "Test Key",
		ExpiresAt:  time.Now().Add(24 * time.Hour),
		CreatedAt:  time.Now(),
	}

	err = apiKeyRepo.Create(context.Background(), apiKey)
	if err != nil {
		t.Fatalf("Failed to create API key: %v", err)
	}

	// Delete user
	err = service.DeleteUser(context.Background(), user.ID)

	// Check results
	if err != nil {
		t.Errorf("DeleteUser() error = %v", err)
	}

	// Check that user was deleted
	_, err = userRepo.GetByID(context.Background(), user.ID)
	if err == nil {
		t.Error("Expected error for deleted user")
	}

	// Check that sessions were deleted
	sessions, err := sessionRepo.GetActiveByUserID(context.Background(), user.ID)
	if err != nil {
		t.Errorf("Failed to get active sessions: %v", err)
	}

	if len(sessions) != 0 {
		t.Errorf("Expected 0 active sessions after user deletion, got %d", len(sessions))
	}

	// Check that API keys were deleted
	apiKeys, err := apiKeyRepo.GetByUserID(context.Background(), user.ID)
	if err != nil {
		t.Errorf("Failed to get API keys: %v", err)
	}

	if len(apiKeys) != 0 {
		t.Errorf("Expected 0 API keys after user deletion, got %d", len(apiKeys))
	}

	// Test with non-existent user
	err = service.DeleteUser(context.Background(), 999)

	// Check that we get a not found error
	if err == nil {
		t.Error("Expected error for non-existent user")
	}
}

func TestUserService_CheckUsername(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	passwordCfg := auth.DefaultPasswordConfig()

	service := NewUserService(userRepo, sessionRepo, apiKeyRepo, passwordCfg)

	// Create a test user
	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed-password",
		Salt:         "salt-value",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Check existing username
	available, err := service.CheckUsername(context.Background(), "testuser")

	// Check results
	if err != nil {
		t.Errorf("CheckUsername() error = %v", err)
	}

	if available {
		t.Error("Expected username to be unavailable")
	}

	// Check non-existent username
	available, err = service.CheckUsername(context.Background(), "newusername")

	// Check results
	if err != nil {
		t.Errorf("CheckUsername() error = %v", err)
	}

	if !available {
		t.Error("Expected username to be available")
	}

	// Test with invalid username
	_, err = service.CheckUsername(context.Background(), "a")

	// Check that we get a validation error
	if err == nil {
		t.Error("Expected error for invalid username")
	}
}

func TestUserService_CheckEmail(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	passwordCfg := auth.DefaultPasswordConfig()

	service := NewUserService(userRepo, sessionRepo, apiKeyRepo, passwordCfg)

	// Create a test user
	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed-password",
		Salt:         "salt-value",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Check existing email
	available, err := service.CheckEmail(context.Background(), "test@example.com")

	// Check results
	if err != nil {
		t.Errorf("CheckEmail() error = %v", err)
	}

	if available {
		t.Error("Expected email to be unavailable")
	}

	// Check non-existent email
	available, err = service.CheckEmail(context.Background(), "new@example.com")

	// Check results
	if err != nil {
		t.Errorf("CheckEmail() error = %v", err)
	}

	if !available {
		t.Error("Expected email to be available")
	}

	// Test with invalid email
	_, err = service.CheckEmail(context.Background(), "invalid-email")

	// Check that we get a validation error
	if err == nil {
		t.Error("Expected error for invalid email")
	}
}

func TestUserService_GetUserActiveSessions(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	passwordCfg := auth.DefaultPasswordConfig()

	service := NewUserService(userRepo, sessionRepo, apiKeyRepo, passwordCfg)

	// Create a test user
	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed-password",
		Salt:         "salt-value",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Create active and expired sessions
	activeSession1 := &models.Session{
		ID:        "active1",
		UserID:    user.ID,
		JWTID:     "active-jwt1",
		ExpiresAt: time.Now().Add(24 * time.Hour),
		CreatedAt: time.Now(),
	}

	err = sessionRepo.Create(context.Background(), activeSession1)
	if err != nil {
		t.Fatalf("Failed to create active session: %v", err)
	}

	activeSession2 := &models.Session{
		ID:        "active2",
		UserID:    user.ID,
		JWTID:     "active-jwt2",
		ExpiresAt: time.Now().Add(48 * time.Hour),
		CreatedAt: time.Now(),
	}

	err = sessionRepo.Create(context.Background(), activeSession2)
	if err != nil {
		t.Fatalf("Failed to create active session: %v", err)
	}

	expiredSession := &models.Session{
		ID:        "expired",
		UserID:    user.ID,
		JWTID:     "expired-jwt",
		ExpiresAt: time.Now().Add(-24 * time.Hour),
		CreatedAt: time.Now().Add(-48 * time.Hour),
	}

	err = sessionRepo.Create(context.Background(), expiredSession)
	if err != nil {
		t.Fatalf("Failed to create expired session: %v", err)
	}

	// Get active sessions
	activeSessions, err := service.GetUserActiveSessions(context.Background(), user.ID)

	// Check results
	if err != nil {
		t.Errorf("GetUserActiveSessions() error = %v", err)
	}

	if len(activeSessions) != 2 {
		t.Errorf("Expected 2 active sessions, got %d", len(activeSessions))
	}

	// Check that the returned objects are properly structured
	for _, session := range activeSessions {
		if session.ID == "" {
			t.Error("Expected non-empty ID in active session info")
		}

		if session.CreatedAt.IsZero() {
			t.Error("Expected non-zero CreatedAt in active session info")
		}

		if session.ExpiresAt.IsZero() {
			t.Error("Expected non-zero ExpiresAt in active session info")
		}
	}
}

func TestUserService_InvalidateSession(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	passwordCfg := auth.DefaultPasswordConfig()

	service := NewUserService(userRepo, sessionRepo, apiKeyRepo, passwordCfg)

	// Create a test user
	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed-password",
		Salt:         "salt-value",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Create a session
	session := &models.Session{
		ID:        "testsession",
		UserID:    user.ID,
		JWTID:     "testjwt",
		ExpiresAt: time.Now().Add(24 * time.Hour),
		CreatedAt: time.Now(),
	}

	err = sessionRepo.Create(context.Background(), session)
	if err != nil {
		t.Fatalf("Failed to create session: %v", err)
	}

	// Create a session for another user
	otherUser := &models.User{
		Username:     "otheruser",
		Email:        "other@example.com",
		PasswordHash: "hashed-password",
		Salt:         "salt-value",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	err = userRepo.Create(context.Background(), otherUser)
	if err != nil {
		t.Fatalf("Failed to create other user: %v", err)
	}

	otherSession := &models.Session{
		ID:        "othersession",
		UserID:    otherUser.ID,
		JWTID:     "otherjwt",
		ExpiresAt: time.Now().Add(24 * time.Hour),
		CreatedAt: time.Now(),
	}

	err = sessionRepo.Create(context.Background(), otherSession)
	if err != nil {
		t.Fatalf("Failed to create other session: %v", err)
	}

	// Invalidate user's session
	err = service.InvalidateSession(context.Background(), user.ID, session.ID)

	// Check results
	if err != nil {
		t.Errorf("InvalidateSession() error = %v", err)
	}

	// Check that session was deleted
	_, err = sessionRepo.GetByID(context.Background(), session.ID)
	if err == nil {
		t.Error("Expected error for deleted session")
	}

	// Try to invalidate other user's session
	err = service.InvalidateSession(context.Background(), user.ID, otherSession.ID)

	// Check that we get a forbidden error
	if err == nil {
		t.Error("Expected error for invalidating someone else's session")
	}

	// Try to invalidate non-existent session
	err = service.InvalidateSession(context.Background(), user.ID, "nonexistent")

	// Check that we get a not found error
	if err == nil {
		t.Error("Expected error for non-existent session")
	}
}

func TestUserService_UpdateUser(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	passwordCfg := auth.DefaultPasswordConfig()

	service := NewUserService(userRepo, sessionRepo, apiKeyRepo, passwordCfg)

	// Create a test user
	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed-password",
		Salt:         "salt-value",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Create another user to test duplicate checks
	otherUser := &models.User{
		Username:     "otheruser",
		Email:        "other@example.com",
		PasswordHash: "hashed-password",
		Salt:         "salt-value",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	err = userRepo.Create(context.Background(), otherUser)
	if err != nil {
		t.Fatalf("Failed to create other user: %v", err)
	}

	// Test cases
	tests := []struct {
		name        string
		userID      int64
		update      *models.UserUpdate
		expectError bool
		checkFields func(t *testing.T, user *models.User)
	}{
		{
			name:   "Update username",
			userID: user.ID,
			update: &models.UserUpdate{
				Username: "newusername",
			},
			expectError: false,
			checkFields: func(t *testing.T, u *models.User) {
				if u.Username != "newusername" {
					t.Errorf("Expected username = %s, got %s", "newusername", u.Username)
				}
			},
		},
		{
			name:   "Update email",
			userID: user.ID,
			update: &models.UserUpdate{
				Email: "new@example.com",
			},
			expectError: false,
			checkFields: func(t *testing.T, u *models.User) {
				if u.Email != "new@example.com" {
					t.Errorf("Expected email = %s, got %s", "new@example.com", u.Email)
				}
			},
		},
		{
			name:   "Update both username and email",
			userID: user.ID,
			update: &models.UserUpdate{
				Username: "newestname",
				Email:    "newest@example.com",
			},
			expectError: false,
			checkFields: func(t *testing.T, u *models.User) {
				if u.Username != "newestname" {
					t.Errorf("Expected username = %s, got %s", "newestname", u.Username)
				}
				if u.Email != "newest@example.com" {
					t.Errorf("Expected email = %s, got %s", "newest@example.com", u.Email)
				}
			},
		},
		{
			name:        "Update with no changes",
			userID:      user.ID,
			update:      &models.UserUpdate{},
			expectError: false,
			checkFields: func(t *testing.T, u *models.User) {
				// No changes expected
			},
		},
		{
			name:   "Update with duplicate username",
			userID: user.ID,
			update: &models.UserUpdate{
				Username: "otheruser", // This username is already taken
			},
			expectError: true,
			checkFields: nil,
		},
		{
			name:   "Update with duplicate email",
			userID: user.ID,
			update: &models.UserUpdate{
				Email: "other@example.com", // This email is already taken
			},
			expectError: true,
			checkFields: nil,
		},
		{
			name:   "Update non-existent user",
			userID: 999, // Non-existent user ID
			update: &models.UserUpdate{
				Username: "doesntmatter",
			},
			expectError: true,
			checkFields: nil,
		},
	}

	// Run tests
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			updatedUser, err := service.UpdateUser(context.Background(), tt.userID, tt.update)

			if tt.expectError {
				if err == nil {
					t.Errorf("Expected error but got nil")
				}
				return
			}

			if err != nil {
				t.Errorf("Unexpected error: %v", err)
				return
			}

			if updatedUser == nil {
				t.Fatal("Expected non-nil user")
				return
			}

			// Verify fields were updated correctly
			if tt.checkFields != nil {
				tt.checkFields(t, updatedUser)
			}

			// Check that sensitive information is sanitized
			if updatedUser.PasswordHash != "" {
				t.Error("Expected empty PasswordHash in sanitized user")
			}

			if updatedUser.Salt != "" {
				t.Error("Expected empty Salt in sanitized user")
			}
		})
	}
}

func TestUserService_ChangePassword(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	passwordCfg := auth.DefaultPasswordConfig()

	service := NewUserService(userRepo, sessionRepo, apiKeyRepo, passwordCfg)

	// Create a test user
	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed-password",
		Salt:         "salt-value",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Create sessions for the user
	session1 := &models.Session{
		ID:        "session1",
		UserID:    user.ID,
		JWTID:     "jwt1",
		ExpiresAt: time.Now().Add(24 * time.Hour),
		CreatedAt: time.Now(),
	}

	err = sessionRepo.Create(context.Background(), session1)
	if err != nil {
		t.Fatalf("Failed to create session: %v", err)
	}

	session2 := &models.Session{
		ID:        "session2",
		UserID:    user.ID,
		JWTID:     "jwt2",
		ExpiresAt: time.Now().Add(24 * time.Hour),
		CreatedAt: time.Now(),
	}

	err = sessionRepo.Create(context.Background(), session2)
	if err != nil {
		t.Fatalf("Failed to create session: %v", err)
	}

	// Test valid password change
	t.Run("Valid password change", func(t *testing.T) {
		err := service.ChangePassword(context.Background(), user.ID, "NewValidPassword123!")
		if err != nil {
			t.Errorf("ChangePassword() error = %v", err)
			return
		}

		// Check that user's password was updated
		updatedUser, err := userRepo.GetByID(context.Background(), user.ID)
		if err != nil {
			t.Errorf("Failed to get updated user: %v", err)
			return
		}

		if updatedUser.PasswordHash == "hashed-password" {
			t.Error("Expected password hash to change")
		}

		// Verify all sessions were invalidated
		sessions, err := sessionRepo.GetActiveByUserID(context.Background(), user.ID)
		if err != nil {
			t.Errorf("Failed to get active sessions: %v", err)
			return
		}

		if len(sessions) != 0 {
			t.Errorf("Expected 0 active sessions after password change, got %d", len(sessions))
		}
	})

	// Reset the user and sessions for next test
	user.PasswordHash = "hashed-password"
	user.Salt = "salt-value"
	err = userRepo.Update(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to reset user: %v", err)
	}

	// Recreate the sessions
	err = sessionRepo.Create(context.Background(), session1)
	if err != nil {
		t.Fatalf("Failed to recreate session: %v", err)
	}

	err = sessionRepo.Create(context.Background(), session2)
	if err != nil {
		t.Fatalf("Failed to recreate session: %v", err)
	}

	// Test invalid password
	t.Run("Invalid password", func(t *testing.T) {
		err := service.ChangePassword(context.Background(), user.ID, "short")
		if err == nil {
			t.Error("Expected error for invalid password, got nil")
			return
		}

		// Verify sessions were not invalidated
		sessions, err := sessionRepo.GetActiveByUserID(context.Background(), user.ID)
		if err != nil {
			t.Errorf("Failed to get active sessions: %v", err)
			return
		}

		if len(sessions) != 2 {
			t.Errorf("Expected 2 active sessions, got %d", len(sessions))
		}
	})

	// Test non-existent user
	t.Run("Non-existent user", func(t *testing.T) {
		err := service.ChangePassword(context.Background(), 999, "ValidPassword123!")
		if err == nil {
			t.Error("Expected error for non-existent user, got nil")
		}
	})

	// Test with password hashing error
	t.Run("Password hashing error", func(t *testing.T) {

	})
}
