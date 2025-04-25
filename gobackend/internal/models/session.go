// Package models provides data structures and operations for the HideMe application.
// This file contains models related to user authentication sessions and token management.
// The session management system supports secure authentication with token tracking
// and invalidation capabilities for enhanced security.
package models

import (
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// Session represents a user authentication session.
// It is used to track active JWT tokens and enable logout functionality.
// Sessions provide better security by allowing token invalidation and
// monitoring of active authentications across devices.
type Session struct {
	// ID is the unique identifier for this session
	ID string `json:"id" db:"session_id"`

	// UserID references the user who owns this session
	UserID int64 `json:"user_id" db:"user_id"`

	// JWTID stores the unique identifier of the JWT token associated with this session
	// This enables tracking and revocation of specific tokens
	JWTID string `json:"jwt_id" db:"jwt_id"`

	// ExpiresAt defines when this session will automatically expire
	ExpiresAt time.Time `json:"expires_at" db:"expires_at"`

	// CreatedAt records when this session was initiated
	CreatedAt time.Time `json:"created_at" db:"created_at"`
}

// TableName returns the database table name for the Session model.
// This method is used by ORM frameworks to determine where to persist this entity.
func (s *Session) TableName() string {
	return constants.TableSessions
}

// NewSession creates a new Session with the given parameters.
//
// Parameters:
//   - userID: The ID of the user who owns this session
//   - jwtID: The unique identifier of the JWT token associated with this session
//   - expiryDuration: How long this session should remain valid
//
// Returns:
//   - A new Session pointer with all fields populated
//
// This function automatically sets the creation time and calculates the expiry time
// based on the provided duration, ensuring consistent session lifecycle management.
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
//
// Returns:
//   - true if the current time is after the expiry time, false otherwise
//
// This method helps maintain security by ensuring expired sessions are not accepted,
// preventing unauthorized access through outdated tokens.
func (s *Session) IsExpired() bool {
	return time.Now().After(s.ExpiresAt)
}

// ActiveSessionInfo represents summary information about an active session.
// This is used for displaying active sessions to the user for management purposes,
// allowing users to monitor and control their authenticated sessions across devices.
type ActiveSessionInfo struct {
	// ID is the unique identifier for this session
	ID string `json:"id"`

	// CreatedAt records when this session was initiated
	CreatedAt time.Time `json:"created_at"`

	// ExpiresAt defines when this session will automatically expire
	ExpiresAt time.Time `json:"expires_at"`

	// Device and location information could be added in the future to enhance
	// security awareness and enable more informed session management
}
