package models

import (
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// Session represents a user authentication session.
// It is used to track active JWT tokens and enable logout functionality.
type Session struct {
	ID        string    `json:"id" db:"session_id"`
	UserID    int64     `json:"user_id" db:"user_id"`
	JWTID     string    `json:"jwt_id" db:"jwt_id"`
	ExpiresAt time.Time `json:"expires_at" db:"expires_at"`
	CreatedAt time.Time `json:"created_at" db:"created_at"`
}

// TableName returns the database table name for the Session model.
func (s *Session) TableName() string {
	return constants.TableSessions
}

// NewSession creates a new Session with the given parameters.
func NewSession(userID int64, jwtID string, expiryDuration time.Duration) *Session {
	now := time.Now()
	return &Session{
		UserID:    userID,
		JWTID:     jwtID,
		ExpiresAt: now.Add(expiryDuration),
		CreatedAt: now,
	}
}

// IsExpired checks if the session has expired.
func (s *Session) IsExpired() bool {
	return time.Now().After(s.ExpiresAt)
}

// ActiveSessionInfo represents summary information about an active session.
// This is used for displaying active sessions to the user.
type ActiveSessionInfo struct {
	ID        string    `json:"id"`
	CreatedAt time.Time `json:"created_at"`
	ExpiresAt time.Time `json:"expires_at"`
	// Device and location information could be added in the future
}
