package models_test

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestSession_TableName(t *testing.T) {
	// Create a test session
	session := &models.Session{
		ID:        "session123",
		UserID:    100,
		JWTID:     "jwt456",
		ExpiresAt: time.Now().Add(time.Hour),
		CreatedAt: time.Now(),
	}

	// Verify the table name
	tableName := session.TableName()
	assert.Equal(t, "sessions", tableName, "TableName should return the correct database table name")
}

func TestNewSession(t *testing.T) {
	// Test parameters
	userID := int64(100)
	jwtID := "jwt456"
	expiryDuration := 24 * time.Hour

	// Create a new session
	now := time.Now()
	session := models.NewSession(userID, jwtID, expiryDuration)

	// Verify the session was created correctly
	assert.NotNil(t, session, "NewSession should return a non-nil Session")
	assert.Equal(t, userID, session.UserID, "Session should have the provided user ID")
	assert.Equal(t, jwtID, session.JWTID, "Session should have the provided JWT ID")
	assert.WithinDuration(t, now.Add(expiryDuration), session.ExpiresAt, time.Second, "ExpiresAt should be set to now + expiry duration")
	assert.WithinDuration(t, now, session.CreatedAt, time.Second, "CreatedAt should be set to current time")
	assert.Equal(t, "", session.ID, "A new Session should have empty ID until explicitly set or saved to database")
}

func TestSession_IsExpired(t *testing.T) {
	testCases := []struct {
		name            string
		expiresAt       time.Time
		shouldBeExpired bool
	}{
		{"Future expiry", time.Now().Add(time.Hour), false},
		{"Past expiry", time.Now().Add(-time.Hour), true},
	}

	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			// Create a session with the test expiry time
			session := &models.Session{
				ID:        "session123",
				UserID:    100,
				JWTID:     "jwt456",
				ExpiresAt: tc.expiresAt,
				CreatedAt: time.Now().Add(-24 * time.Hour), // Created a day ago
			}

			// Check if the session is expired
			isExpired := session.IsExpired()
			assert.Equal(t, tc.shouldBeExpired, isExpired, "IsExpired should correctly determine if the session has expired")
		})
	}
}

func TestActiveSessionInfo(t *testing.T) {
	// Create a test active session info
	now := time.Now()
	sessionInfo := &models.ActiveSessionInfo{
		ID:        "session123",
		CreatedAt: now,
		ExpiresAt: now.Add(time.Hour),
	}

	// Verify the fields
	assert.Equal(t, "session123", sessionInfo.ID)
	assert.Equal(t, now, sessionInfo.CreatedAt)
	assert.Equal(t, now.Add(time.Hour), sessionInfo.ExpiresAt)
}
