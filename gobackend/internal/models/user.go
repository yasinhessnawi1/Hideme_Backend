package models

import (
	"time"
)

// User represents a registered user of the HideMe application.
// It contains authentication information and core user attributes.
type User struct {
	ID           int64     `json:"id" db:"user_id"`
	Username     string    `json:"username" db:"username" validate:"required,min=3,max=50"`
	Email        string    `json:"email" db:"email" validate:"required,email"`
	PasswordHash string    `json:"-" db:"password_hash"`
	Salt         string    `json:"-" db:"salt"`
	CreatedAt    time.Time `json:"created_at" db:"created_at"`
	UpdatedAt    time.Time `json:"updated_at" db:"updated_at"`
}

// NewUser creates a new User instance with the given username and email.
// Password fields are populated later during the registration process.
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
func (u *User) TableName() string {
	return "users"
}

// Sanitize removes sensitive information from the User object when sending to clients.
// This ensures sensitive fields like password hash are never exposed.
func (u *User) Sanitize() *User {
	sanitized := *u
	sanitized.PasswordHash = ""
	sanitized.Salt = ""
	return &sanitized
}

// UserCredentials represents the login credentials provided by a user.
type UserCredentials struct {
	Username string `json:"username" validate:"required_without=Email,omitempty,min=3,max=50"`
	Email    string `json:"email" validate:"required_without=Username,omitempty,email"`
	Password string `json:"password" validate:"required,min=8"`
}

// UserRegistration represents the data required for user registration.
type UserRegistration struct {
	Username        string `json:"username" validate:"required,min=3,max=50"`
	Email           string `json:"email" validate:"required,email"`
	Password        string `json:"password" validate:"required,min=8"`
	ConfirmPassword string `json:"confirm_password" validate:"required,eqfield=Password"`
}

// UserUpdate represents the data that can be updated for a user.
type UserUpdate struct {
	Username string `json:"username" validate:"omitempty,min=3,max=50"`
	Email    string `json:"email" validate:"omitempty,email"`
	Password string `json:"password" validate:"omitempty,min=8"`
}
