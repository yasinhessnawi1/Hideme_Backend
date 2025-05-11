package models

import (
	"time"
)

// PasswordResetToken represents a password reset token in the database.
type PasswordResetToken struct {
	TokenHash string    `json:"-"` // The hashed token, not sent to client
	UserID    int64     `json:"user_id"`
	ExpiresAt time.Time `json:"expires_at"`
	CreatedAt time.Time `json:"created_at"`
}

// PasswordResetRequest defines the structure for requesting a password reset.
type ForgotPasswordRequest struct {
	Email string `json:"email" validate:"required,email"`
}

// ResetPasswordRequest defines the structure for resetting a password with a token.
type ResetPasswordRequest struct {
	Token       string `json:"token" validate:"required"`
	NewPassword string `json:"new_password" validate:"required,min=8"` // You might want to use your strong_password validation here
}
