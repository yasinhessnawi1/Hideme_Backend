package service

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// Mock implementations for testing
type MockUserRepository struct {
	users           map[int64]*models.User
	usersByUsername map[string]*models.User
	usersByEmail    map[string]*models.User
	nextID          int64
}

func NewMockUserRepository() *MockUserRepository {
	return &MockUserRepository{
		users:           make(map[int64]*models.User),
		usersByUsername: make(map[string]*models.User),
		usersByEmail:    make(map[string]*models.User),
		nextID:          1,
	}
}

func (m *MockUserRepository) Create(ctx context.Context, user *models.User) error {
	user.ID = m.nextID
	m.nextID++

	m.users[user.ID] = user
	m.usersByUsername[user.Username] = user
	m.usersByEmail[user.Email] = user

	return nil
}

func (m *MockUserRepository) GetByID(ctx context.Context, id int64) (*models.User, error) {
	user, ok := m.users[id]
	if !ok {
		return nil, utils.NewNotFoundError("User", id)
	}
	return user, nil
}

func (m *MockUserRepository) GetByUsername(ctx context.Context, username string) (*models.User, error) {
	user, ok := m.usersByUsername[username]
	if !ok {
		return nil, utils.NewNotFoundError("User", username)
	}
	return user, nil
}

func (m *MockUserRepository) GetByEmail(ctx context.Context, email string) (*models.User, error) {
	user, ok := m.usersByEmail[email]
	if !ok {
		return nil, utils.NewNotFoundError("User", email)
	}
	return user, nil
}

func (m *MockUserRepository) Update(ctx context.Context, user *models.User) error {
	if _, ok := m.users[user.ID]; !ok {
		return utils.NewNotFoundError("User", user.ID)
	}

	m.users[user.ID] = user
	m.usersByUsername[user.Username] = user
	m.usersByEmail[user.Email] = user

	return nil
}

func (m *MockUserRepository) Delete(ctx context.Context, id int64) error {
	user, ok := m.users[id]
	if !ok {
		return utils.NewNotFoundError("User", id)
	}

	delete(m.usersByUsername, user.Username)
	delete(m.usersByEmail, user.Email)
	delete(m.users, id)

	return nil
}

func (m *MockUserRepository) ChangePassword(ctx context.Context, id int64, passwordHash, salt string) error {
	user, ok := m.users[id]
	if !ok {
		return utils.NewNotFoundError("User", id)
	}

	user.PasswordHash = passwordHash
	user.Salt = salt

	return nil
}

func (m *MockUserRepository) ExistsByUsername(ctx context.Context, username string) (bool, error) {
	_, ok := m.usersByUsername[username]
	return ok, nil
}

func (m *MockUserRepository) ExistsByEmail(ctx context.Context, email string) (bool, error) {
	_, ok := m.usersByEmail[email]
	return ok, nil
}

type MockSessionRepository struct {
	sessions        map[string]*models.Session
	sessionsByJWTID map[string]*models.Session
	sessionsByUser  map[int64][]*models.Session
}

func NewMockSessionRepository() *MockSessionRepository {
	return &MockSessionRepository{
		sessions:        make(map[string]*models.Session),
		sessionsByJWTID: make(map[string]*models.Session),
		sessionsByUser:  make(map[int64][]*models.Session),
	}
}

func (m *MockSessionRepository) Create(ctx context.Context, session *models.Session) error {
	m.sessions[session.ID] = session
	m.sessionsByJWTID[session.JWTID] = session

	m.sessionsByUser[session.UserID] = append(m.sessionsByUser[session.UserID], session)

	return nil
}

func (m *MockSessionRepository) GetByID(ctx context.Context, id string) (*models.Session, error) {
	session, ok := m.sessions[id]
	if !ok {
		return nil, utils.NewNotFoundError("Session", id)
	}
	return session, nil
}

func (m *MockSessionRepository) GetByJWTID(ctx context.Context, jwtID string) (*models.Session, error) {
	session, ok := m.sessionsByJWTID[jwtID]
	if !ok {
		return nil, utils.NewNotFoundError("Session", jwtID)
	}
	return session, nil
}

func (m *MockSessionRepository) GetActiveByUserID(ctx context.Context, userID int64) ([]*models.Session, error) {
	sessions := m.sessionsByUser[userID]

	var activeSessions []*models.Session
	now := time.Now()

	for _, session := range sessions {
		if session.ExpiresAt.After(now) {
			activeSessions = append(activeSessions, session)
		}
	}

	return activeSessions, nil
}

func (m *MockSessionRepository) Delete(ctx context.Context, id string) error {
	session, ok := m.sessions[id]
	if !ok {
		return utils.NewNotFoundError("Session", id)
	}

	delete(m.sessionsByJWTID, session.JWTID)
	delete(m.sessions, id)

	// Remove from user sessions
	var userSessions []*models.Session
	for _, s := range m.sessionsByUser[session.UserID] {
		if s.ID != id {
			userSessions = append(userSessions, s)
		}
	}

	m.sessionsByUser[session.UserID] = userSessions

	return nil
}

func (m *MockSessionRepository) DeleteByJWTID(ctx context.Context, jwtID string) error {
	session, ok := m.sessionsByJWTID[jwtID]
	if !ok {
		return utils.NewNotFoundError("Session", jwtID)
	}

	return m.Delete(ctx, session.ID)
}

func (m *MockSessionRepository) DeleteByUserID(ctx context.Context, userID int64) error {
	sessions, ok := m.sessionsByUser[userID]
	if !ok {
		return nil
	}

	for _, session := range sessions {
		delete(m.sessions, session.ID)
		delete(m.sessionsByJWTID, session.JWTID)
	}

	delete(m.sessionsByUser, userID)

	return nil
}

func (m *MockSessionRepository) DeleteExpired(ctx context.Context) (int64, error) {
	var count int64
	now := time.Now()

	for id, session := range m.sessions {
		if session.ExpiresAt.Before(now) {
			delete(m.sessions, id)
			delete(m.sessionsByJWTID, session.JWTID)

			// Remove from user sessions
			var userSessions []*models.Session
			for _, s := range m.sessionsByUser[session.UserID] {
				if s.ID != id {
					userSessions = append(userSessions, s)
				}
			}

			m.sessionsByUser[session.UserID] = userSessions

			count++
		}
	}

	return count, nil
}

func (m *MockSessionRepository) IsValidSession(ctx context.Context, jwtID string) (bool, error) {
	session, ok := m.sessionsByJWTID[jwtID]
	if !ok {
		return false, nil
	}

	return session.ExpiresAt.After(time.Now()), nil
}

type MockAPIKeyRepository struct {
	apiKeys       map[string]*models.APIKey
	apiKeysByUser map[int64][]*models.APIKey
}

func NewMockAPIKeyRepository() *MockAPIKeyRepository {
	return &MockAPIKeyRepository{
		apiKeys:       make(map[string]*models.APIKey),
		apiKeysByUser: make(map[int64][]*models.APIKey),
	}
}

func (m *MockAPIKeyRepository) Create(ctx context.Context, apiKey *models.APIKey) error {
	m.apiKeys[apiKey.ID] = apiKey
	m.apiKeysByUser[apiKey.UserID] = append(m.apiKeysByUser[apiKey.UserID], apiKey)

	return nil
}

func (m *MockAPIKeyRepository) GetByID(ctx context.Context, id string) (*models.APIKey, error) {
	apiKey, ok := m.apiKeys[id]
	if !ok {
		return nil, utils.NewNotFoundError("APIKey", id)
	}
	return apiKey, nil
}

func (m *MockAPIKeyRepository) GetByUserID(ctx context.Context, userID int64) ([]*models.APIKey, error) {
	return m.apiKeysByUser[userID], nil
}

func (m *MockAPIKeyRepository) VerifyKey(ctx context.Context, keyID, keyHash string) (*models.APIKey, error) {
	apiKey, ok := m.apiKeys[keyID]
	if !ok {
		return nil, utils.NewNotFoundError("APIKey", keyID)
	}

	if apiKey.APIKeyHash != keyHash {
		return nil, utils.NewInvalidTokenError()
	}

	if apiKey.IsExpired() {
		return nil, utils.NewExpiredTokenError()
	}

	return apiKey, nil
}

func (m *MockAPIKeyRepository) Delete(ctx context.Context, id string) error {
	apiKey, ok := m.apiKeys[id]
	if !ok {
		return utils.NewNotFoundError("APIKey", id)
	}

	delete(m.apiKeys, id)

	// Remove from user API keys
	var userAPIKeys []*models.APIKey
	for _, key := range m.apiKeysByUser[apiKey.UserID] {
		if key.ID != id {
			userAPIKeys = append(userAPIKeys, key)
		}
	}

	m.apiKeysByUser[apiKey.UserID] = userAPIKeys

	return nil
}

func (m *MockAPIKeyRepository) DeleteByUserID(ctx context.Context, userID int64) error {
	apiKeys, ok := m.apiKeysByUser[userID]
	if !ok {
		return nil
	}

	for _, apiKey := range apiKeys {
		delete(m.apiKeys, apiKey.ID)
	}

	delete(m.apiKeysByUser, userID)

	return nil
}

func (m *MockAPIKeyRepository) DeleteExpired(ctx context.Context) (int64, error) {
	var count int64
	now := time.Now()

	for id, apiKey := range m.apiKeys {
		if apiKey.ExpiresAt.Before(now) {
			delete(m.apiKeys, id)

			// Remove from user API keys
			var userAPIKeys []*models.APIKey
			for _, key := range m.apiKeysByUser[apiKey.UserID] {
				if key.ID != id {
					userAPIKeys = append(userAPIKeys, key)
				}
			}

			m.apiKeysByUser[apiKey.UserID] = userAPIKeys

			count++
		}
	}

	return count, nil
}

func TestNewAuthService(t *testing.T) {
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	jwtService := auth.NewJWTService(&config.JWTSettings{})
	passwordCfg := auth.DefaultPasswordConfig()
	apiKeyCfg := &config.APIKeySettings{}

	service := NewAuthService(userRepo, sessionRepo, apiKeyRepo, jwtService, passwordCfg, apiKeyCfg)

	if service == nil {
		t.Error("Expected non-nil service")
	}
}

func TestAuthService_RegisterUser(t *testing.T) {

}

func TestAuthService_AuthenticateUser(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	jwtService := auth.NewJWTService(&config.JWTSettings{
		Secret:        "test-secret",
		Expiry:        15 * time.Minute,
		RefreshExpiry: 7 * 24 * time.Hour,
		Issuer:        "test-issuer",
	})
	passwordCfg := &auth.PasswordConfig{
		Memory:      16 * 1024, // Use minimal settings for faster tests
		Iterations:  1,
		Parallelism: 1,
		SaltLength:  16,
		KeyLength:   32,
	}
	apiKeyCfg := &config.APIKeySettings{}

	service := NewAuthService(userRepo, sessionRepo, apiKeyRepo, jwtService, passwordCfg, apiKeyCfg)

	// Create a test user with a known password
	testPassword := "password123"
	hash, salt, err := auth.HashPassword(testPassword, passwordCfg)
	if err != nil {
		t.Fatalf("Failed to hash password: %v", err)
	}

	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: hash,
		Salt:         salt,
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	err = userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Test authentication with username
	creds := &models.UserCredentials{
		Username: "testuser",
		Password: testPassword,
	}

	authenticatedUser, accessToken, refreshToken, err := service.AuthenticateUser(context.Background(), creds)

	// Check results
	if err != nil {
		t.Errorf("AuthenticateUser() error = %v", err)
	}

	if authenticatedUser == nil {
		t.Fatal("Expected non-nil user")
	}

	if authenticatedUser.ID != user.ID {
		t.Errorf("Expected ID = %d, got %d", user.ID, authenticatedUser.ID)
	}

	if accessToken == "" {
		t.Error("Expected non-empty access token")
	}

	if refreshToken == "" {
		t.Error("Expected non-empty refresh token")
	}

	// Check that a session was created
	sessions, err := sessionRepo.GetActiveByUserID(context.Background(), user.ID)
	if err != nil {
		t.Errorf("Failed to get active sessions: %v", err)
	}

	if len(sessions) != 1 {
		t.Errorf("Expected 1 active session, got %d", len(sessions))
	}

	// Test authentication with email
	creds = &models.UserCredentials{
		Email:    "test@example.com",
		Password: testPassword,
	}

	_, _, _, err = service.AuthenticateUser(context.Background(), creds)

	// Check results
	if err != nil {
		t.Errorf("AuthenticateUser() with email error = %v", err)
	}

	// Test with wrong password
	creds.Password = "wrongpassword"
	_, _, _, err = service.AuthenticateUser(context.Background(), creds)

	// Check that we get an invalid credentials error
	if err == nil {
		t.Error("Expected error for wrong password")
	}

	// Test with non-existent user
	creds.Email = "nonexistent@example.com"
	creds.Username = ""
	_, _, _, err = service.AuthenticateUser(context.Background(), creds)

	// Check that we get an invalid credentials error
	if err == nil {
		t.Error("Expected error for non-existent user")
	}

	// Test with missing credentials
	creds.Email = ""
	_, _, _, err = service.AuthenticateUser(context.Background(), creds)

	// Check that we get a validation error
	if err == nil {
		t.Error("Expected error for missing credentials")
	}
}

func TestAuthService_RefreshTokens(t *testing.T) {

}

func TestAuthService_Logout(t *testing.T) {

}

func TestAuthService_LogoutAll(t *testing.T) {

}

func TestAuthService_CreateAPIKey(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	jwtService := auth.NewJWTService(&config.JWTSettings{})
	passwordCfg := auth.DefaultPasswordConfig()
	apiKeyCfg := &config.APIKeySettings{
		DefaultExpiry: 90 * 24 * time.Hour, // 90 days
	}

	service := NewAuthService(userRepo, sessionRepo, apiKeyRepo, jwtService, passwordCfg, apiKeyCfg)

	// Create a test user
	user := &models.User{
		Username:  "testuser",
		Email:     "test@example.com",
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Create API key
	name := "Test API Key"
	duration := 30 * 24 * time.Hour // 30 days

	rawKey, apiKey, err := service.CreateAPIKey(context.Background(), user.ID, name, duration)

	// Check results
	if err != nil {
		t.Errorf("CreateAPIKey() error = %v", err)
	}

	if rawKey == "" {
		t.Error("Expected non-empty raw key")
	}

	if apiKey == nil {
		t.Fatal("Expected non-nil API key")
	}

	if apiKey.Name != name {
		t.Errorf("Expected Name = %s, got %s", name, apiKey.Name)
	}

	if apiKey.UserID != user.ID {
		t.Errorf("Expected UserID = %d, got %d", user.ID, apiKey.UserID)
	}

	// Check expiry time (with tolerance for test execution time)
	expectedExpiry := time.Now().Add(duration)
	tolerance := 5 * time.Second

	if apiKey.ExpiresAt.Before(expectedExpiry.Add(-tolerance)) ||
		apiKey.ExpiresAt.After(expectedExpiry.Add(tolerance)) {
		t.Errorf("ExpiresAt not within expected range: got %v, want ~%v",
			apiKey.ExpiresAt, expectedExpiry)
	}

	// Verify that the API key was saved
	apiKeys, err := apiKeyRepo.GetByUserID(context.Background(), user.ID)
	if err != nil {
		t.Errorf("Failed to get API keys: %v", err)
	}

	if len(apiKeys) != 1 {
		t.Errorf("Expected 1 API key, got %d", len(apiKeys))
	}
}

func TestAuthService_ListAPIKeys(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	jwtService := auth.NewJWTService(&config.JWTSettings{})
	passwordCfg := auth.DefaultPasswordConfig()
	apiKeyCfg := &config.APIKeySettings{}

	service := NewAuthService(userRepo, sessionRepo, apiKeyRepo, jwtService, passwordCfg, apiKeyCfg)

	// Create a test user
	user := &models.User{
		Username:  "testuser",
		Email:     "test@example.com",
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Create API keys
	for i := 0; i < 3; i++ {
		apiKey := &models.APIKey{
			ID:         fmt.Sprintf("key%d", i),
			UserID:     user.ID,
			APIKeyHash: fmt.Sprintf("hash%d", i),
			Name:       fmt.Sprintf("Key %d", i),
			ExpiresAt:  time.Now().Add(24 * time.Hour),
			CreatedAt:  time.Now(),
		}

		err := apiKeyRepo.Create(context.Background(), apiKey)
		if err != nil {
			t.Fatalf("Failed to create API key: %v", err)
		}
	}

	// List API keys
	apiKeys, err := service.ListAPIKeys(context.Background(), user.ID)

	// Check results
	if err != nil {
		t.Errorf("ListAPIKeys() error = %v", err)
	}

	if len(apiKeys) != 3 {
		t.Errorf("Expected 3 API keys, got %d", len(apiKeys))
	}

	// Check that sensitive information is removed
	for _, apiKey := range apiKeys {
		if apiKey.APIKeyHash != "" {
			t.Errorf("Expected empty APIKeyHash, got %s", apiKey.APIKeyHash)
		}
	}
}

func TestAuthService_DeleteAPIKey(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	jwtService := auth.NewJWTService(&config.JWTSettings{})
	passwordCfg := auth.DefaultPasswordConfig()
	apiKeyCfg := &config.APIKeySettings{}

	service := NewAuthService(userRepo, sessionRepo, apiKeyRepo, jwtService, passwordCfg, apiKeyCfg)

	// Create a test user
	user := &models.User{
		Username:  "testuser",
		Email:     "test@example.com",
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
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

	// Delete API key
	err = service.DeleteAPIKey(context.Background(), user.ID, apiKey.ID)

	// Check results
	if err != nil {
		t.Errorf("DeleteAPIKey() error = %v", err)
	}

	// Verify that the API key was deleted
	_, err = apiKeyRepo.GetByID(context.Background(), apiKey.ID)
	if err == nil {
		t.Error("Expected error for deleted API key")
	}

	// Test deleting a non-existent API key
	err = service.DeleteAPIKey(context.Background(), user.ID, "nonexistent")

	// Check that we get a not found error
	if err == nil {
		t.Error("Expected error for non-existent API key")
	}

	// Test deleting someone else's API key
	otherUser := &models.User{
		Username:  "otheruser",
		Email:     "other@example.com",
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	err = userRepo.Create(context.Background(), otherUser)
	if err != nil {
		t.Fatalf("Failed to create other user: %v", err)
	}

	otherKey := &models.APIKey{
		ID:         "otherkey",
		UserID:     otherUser.ID,
		APIKeyHash: "otherhash",
		Name:       "Other Key",
		ExpiresAt:  time.Now().Add(24 * time.Hour),
		CreatedAt:  time.Now(),
	}

	err = apiKeyRepo.Create(context.Background(), otherKey)
	if err != nil {
		t.Fatalf("Failed to create other API key: %v", err)
	}

	// Try to delete other user's key
	err = service.DeleteAPIKey(context.Background(), user.ID, otherKey.ID)

	// Check that we get a forbidden error
	if err == nil {
		t.Error("Expected error for deleting someone else's API key")
	}
}

func TestAuthService_VerifyAPIKey(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	jwtService := auth.NewJWTService(&config.JWTSettings{})
	passwordCfg := auth.DefaultPasswordConfig()
	apiKeyCfg := &config.APIKeySettings{}

	service := NewAuthService(userRepo, sessionRepo, apiKeyRepo, jwtService, passwordCfg, apiKeyCfg)

	// Create a test user
	user := &models.User{
		Username:  "testuser",
		Email:     "test@example.com",
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Create an API key
	keyID := "testkey"
	secret := "testsecret"
	apiKeyStr := keyID + "." + secret
	keyHash := auth.HashAPIKey(apiKeyStr)

	apiKey := &models.APIKey{
		ID:         keyID,
		UserID:     user.ID,
		APIKeyHash: keyHash,
		Name:       "Test Key",
		ExpiresAt:  time.Now().Add(24 * time.Hour),
		CreatedAt:  time.Now(),
	}

	err = apiKeyRepo.Create(context.Background(), apiKey)
	if err != nil {
		t.Fatalf("Failed to create API key: %v", err)
	}

	// Verify API key
	apiKeyUser, err := service.VerifyAPIKey(context.Background(), apiKeyStr)

	// Check results
	if err != nil {
		t.Errorf("VerifyAPIKey() error = %v", err)
	}

	if apiKeyUser == nil {
		t.Fatal("Expected non-nil user")
	}

	if apiKeyUser.ID != user.ID {
		t.Errorf("Expected ID = %d, got %d", user.ID, apiKeyUser.ID)
	}

	// Test with invalid API key
	_, err = service.VerifyAPIKey(context.Background(), "invalid-key")

	// Check that we get an invalid token error
	if err == nil {
		t.Error("Expected error for invalid API key")
	}

	// Test with expired API key
	expiredKey := &models.APIKey{
		ID:         "expiredkey",
		UserID:     user.ID,
		APIKeyHash: auth.HashAPIKey("expiredkey.secret"),
		Name:       "Expired Key",
		ExpiresAt:  time.Now().Add(-24 * time.Hour), // Expired
		CreatedAt:  time.Now().Add(-48 * time.Hour),
	}

	err = apiKeyRepo.Create(context.Background(), expiredKey)
	if err != nil {
		t.Fatalf("Failed to create expired API key: %v", err)
	}

	_, err = service.VerifyAPIKey(context.Background(), "expiredkey.secret")

	// Check that we get an expired token error
	if err == nil {
		t.Error("Expected error for expired API key")
	}
}

func TestAuthService_CleanupExpiredSessions(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	jwtService := auth.NewJWTService(&config.JWTSettings{})
	passwordCfg := auth.DefaultPasswordConfig()
	apiKeyCfg := &config.APIKeySettings{}

	service := NewAuthService(userRepo, sessionRepo, apiKeyRepo, jwtService, passwordCfg, apiKeyCfg)

	// Create a test user
	user := &models.User{
		Username:  "testuser",
		Email:     "test@example.com",
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Create active and expired sessions
	activeSession := &models.Session{
		ID:        "active",
		UserID:    user.ID,
		JWTID:     "active-jwt",
		ExpiresAt: time.Now().Add(24 * time.Hour),
		CreatedAt: time.Now(),
	}

	err = sessionRepo.Create(context.Background(), activeSession)
	if err != nil {
		t.Fatalf("Failed to create active session: %v", err)
	}

	expiredSession1 := &models.Session{
		ID:        "expired1",
		UserID:    user.ID,
		JWTID:     "expired-jwt1",
		ExpiresAt: time.Now().Add(-24 * time.Hour),
		CreatedAt: time.Now().Add(-48 * time.Hour),
	}

	err = sessionRepo.Create(context.Background(), expiredSession1)
	if err != nil {
		t.Fatalf("Failed to create expired session: %v", err)
	}

	expiredSession2 := &models.Session{
		ID:        "expired2",
		UserID:    user.ID,
		JWTID:     "expired-jwt2",
		ExpiresAt: time.Now().Add(-1 * time.Hour),
		CreatedAt: time.Now().Add(-2 * time.Hour),
	}

	err = sessionRepo.Create(context.Background(), expiredSession2)
	if err != nil {
		t.Fatalf("Failed to create expired session: %v", err)
	}

	// Cleanup expired sessions
	count, err := service.CleanupExpiredSessions(context.Background())

	// Check results
	if err != nil {
		t.Errorf("CleanupExpiredSessions() error = %v", err)
	}

	if count != 2 {
		t.Errorf("Expected to clean up 2 sessions, got %d", count)
	}

	// Verify that only expired sessions were deleted
	_, err = sessionRepo.GetByID(context.Background(), activeSession.ID)
	if err != nil {
		t.Error("Active session was unexpectedly deleted")
	}

	_, err = sessionRepo.GetByID(context.Background(), expiredSession1.ID)
	if err == nil {
		t.Error("Expired session 1 was not deleted")
	}

	_, err = sessionRepo.GetByID(context.Background(), expiredSession2.ID)
	if err == nil {
		t.Error("Expired session 2 was not deleted")
	}
}

func TestAuthService_CleanupExpiredAPIKeys(t *testing.T) {
	// Setup
	userRepo := NewMockUserRepository()
	sessionRepo := NewMockSessionRepository()
	apiKeyRepo := NewMockAPIKeyRepository()
	jwtService := auth.NewJWTService(&config.JWTSettings{})
	passwordCfg := auth.DefaultPasswordConfig()
	apiKeyCfg := &config.APIKeySettings{}

	service := NewAuthService(userRepo, sessionRepo, apiKeyRepo, jwtService, passwordCfg, apiKeyCfg)

	// Create a test user
	user := &models.User{
		Username:  "testuser",
		Email:     "test@example.com",
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	err := userRepo.Create(context.Background(), user)
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}

	// Create active and expired API keys
	activeKey := &models.APIKey{
		ID:         "active",
		UserID:     user.ID,
		APIKeyHash: "active-hash",
		Name:       "Active Key",
		ExpiresAt:  time.Now().Add(24 * time.Hour),
		CreatedAt:  time.Now(),
	}

	err = apiKeyRepo.Create(context.Background(), activeKey)
	if err != nil {
		t.Fatalf("Failed to create active API key: %v", err)
	}

	expiredKey1 := &models.APIKey{
		ID:         "expired1",
		UserID:     user.ID,
		APIKeyHash: "expired-hash1",
		Name:       "Expired Key 1",
		ExpiresAt:  time.Now().Add(-24 * time.Hour),
		CreatedAt:  time.Now().Add(-48 * time.Hour),
	}

	err = apiKeyRepo.Create(context.Background(), expiredKey1)
	if err != nil {
		t.Fatalf("Failed to create expired API key: %v", err)
	}

	expiredKey2 := &models.APIKey{
		ID:         "expired2",
		UserID:     user.ID,
		APIKeyHash: "expired-hash2",
		Name:       "Expired Key 2",
		ExpiresAt:  time.Now().Add(-1 * time.Hour),
		CreatedAt:  time.Now().Add(-2 * time.Hour),
	}

	err = apiKeyRepo.Create(context.Background(), expiredKey2)
	if err != nil {
		t.Fatalf("Failed to create expired API key: %v", err)
	}

	// Cleanup expired API keys
	count, err := service.CleanupExpiredAPIKeys(context.Background())

	// Check results
	if err != nil {
		t.Errorf("CleanupExpiredAPIKeys() error = %v", err)
	}

	if count != 2 {
		t.Errorf("Expected to clean up 2 API keys, got %d", count)
	}

	// Verify that only expired API keys were deleted
	_, err = apiKeyRepo.GetByID(context.Background(), activeKey.ID)
	if err != nil {
		t.Error("Active API key was unexpectedly deleted")
	}

	_, err = apiKeyRepo.GetByID(context.Background(), expiredKey1.ID)
	if err == nil {
		t.Error("Expired API key 1 was not deleted")
	}

	_, err = apiKeyRepo.GetByID(context.Background(), expiredKey2.ID)
	if err == nil {
		t.Error("Expired API key 2 was not deleted")
	}
}
