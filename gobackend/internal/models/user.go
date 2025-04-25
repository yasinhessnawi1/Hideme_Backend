// Package models provides data structures and operations for the HideMe application.
// This file contains models related to user management, authentication, and
// account operations. The user model follows security best practices including
// password hashing, salting, and sensitive data protection.
package models

import (
	"time"
)

// User represents a registered user of the HideMe application.
// It contains authentication information and core user attributes.
// Sensitive authentication data is excluded from JSON serialization
// to prevent accidental exposure in API responses.
type User struct {
	// ID is the unique identifier for this user
	ID int64 `json:"id" db:"user_id"`

	// Username is the user's chosen display name
	// Must be between 3 and 50 characters
	Username string `json:"username" db:"username" validate:"required,min=3,max=50"`

	// Email is the user's email address for communications and recovery
	// Must be a valid email format
	Email string `json:"email" db:"email" validate:"required,email"`

	// PasswordHash stores the hashed version of the user's password
	// This field is excluded from JSON serialization for security
	PasswordHash string `json:"-" db:"password_hash"`

	// Salt is a unique value used in the password hashing process
	// This field is excluded from JSON serialization for security
	Salt string `json:"-" db:"salt"`

	// CreatedAt records when this user account was created
	CreatedAt time.Time `json:"created_at" db:"created_at"`

	// UpdatedAt records when this user account was last modified
	UpdatedAt time.Time `json:"updated_at" db:"updated_at"`
}

// NewUser creates a new User instance with the given username and email.
// Password fields are populated later during the registration process.
//
// Parameters:
//   - username: The user's chosen display name (3-50 characters)
//   - email: The user's email address (must be valid format)
//
// Returns:
//   - A new User pointer with basic fields populated and timestamps initialized
//
// The password hash and salt fields must be set separately after proper
// cryptographic processing of the user's password.
func NewUser(username, email string) *User {
	now := time.Now()
	return &User{
		Username:  username,
		Email:     email,
		CreatedAt: now,
		UpdatedAt: now,
	}
}

// TableName returns the database table name for the User model.
// This method is used by ORM frameworks to determine where to persist this entity.
func (u *User) TableName() string {
	return "users"
}

// Sanitize removes sensitive information from the User object when sending to clients.
// This ensures sensitive fields like password hash are never exposed.
//
// Returns:
//   - A copy of the User with sensitive fields (PasswordHash, Salt) cleared
//
// This method adds a security layer that prevents accidental exposure of
// authentication data, even if validation or filtering logic fails elsewhere.
func (u *User) Sanitize() *User {
	sanitized := *u
	sanitized.PasswordHash = ""
	sanitized.Salt = ""
	return &sanitized
}

// UserCredentials represents the login credentials provided by a user.
// This structure validates login requests to ensure they contain the
// necessary information for authentication.
type UserCredentials struct {
	// Username is the user's chosen display name
	// Either Username or Email must be provided
	Username string `json:"username" validate:"required_without=Email,omitempty,min=3,max=50"`

	// Email is the user's email address
	// Either Email or Username must be provided
	Email string `json:"email" validate:"required_without=Username,omitempty,email"`

	// Password is the user's plain text password for authentication
	// Must be at least 8 characters
	Password string `json:"password" validate:"required,min=8"`
}

// UserRegistration represents the data required for user registration.
// This structure validates registration requests to ensure they contain
// complete and properly formatted user information.
type UserRegistration struct {
	// Username is the user's chosen display name
	// Must be between 3 and 50 characters
	Username string `json:"username" validate:"required,min=3,max=50"`

	// Email is the user's email address
	// Must be a valid email format
	Email string `json:"email" validate:"required,email"`

	// Password is the user's plain text password
	// Must be at least 8 characters
	Password string `json:"password" validate:"required,min=8"`

	// ConfirmPassword must match Password exactly
	// This ensures the user has entered their intended password correctly
	ConfirmPassword string `json:"confirm_password" validate:"required,eqfield=Password"`
}

// UserUpdate represents the data that can be updated for a user.
// This structure validates user update requests, allowing for partial
// updates where only some fields are modified.
type UserUpdate struct {
	// Username is the user's chosen display name
	// If provided, must be between 3 and 50 characters
	Username string `json:"username" validate:"omitempty,min=3,max=50"`

	// Email is the user's email address
	// If provided, must be a valid email format
	Email string `json:"email" validate:"omitempty,email"`

	// Password is the user's new plain text password
	// If provided, must be at least 8 characters
	Password string `json:"password" validate:"omitempty,min=8"`
}
