package models_test

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

func TestUser_TableName(t *testing.T) {
	// Create a test user
	user := &models.User{
		ID:           1,
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	// Verify the table name
	tableName := user.TableName()
	assert.Equal(t, "users", tableName, "TableName should return the correct database table name")
}

func TestNewUser(t *testing.T) {
	// Test parameters
	username := "testuser"
	email := "test@example.com"

	// Create a new user
	now := time.Now()
	user := models.NewUser(username, email, "user")

	// Verify the user was created correctly
	assert.NotNil(t, user, "NewUser should return a non-nil User")
	assert.Equal(t, username, user.Username, "User should have the provided username")
	assert.Equal(t, email, user.Email, "User should have the provided email")
	assert.Equal(t, "", user.PasswordHash, "PasswordHash should be empty initially")
	assert.Equal(t, "", user.Salt, "Salt should be empty initially")
	assert.WithinDuration(t, now, user.CreatedAt, time.Second, "CreatedAt should be set to current time")
	assert.WithinDuration(t, now, user.UpdatedAt, time.Second, "UpdatedAt should be set to current time")
	assert.Equal(t, int64(0), user.ID, "A new User should have zero ID until saved to database")
}

func TestUser_Sanitize(t *testing.T) {
	// Create a test user with sensitive information
	user := &models.User{
		ID:           1,
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		CreatedAt:    time.Now(),
		UpdatedAt:    time.Now(),
	}

	// Sanitize the user
	sanitizedUser := user.Sanitize()

	// Verify sensitive information is removed
	assert.Equal(t, user.ID, sanitizedUser.ID, "ID should be preserved")
	assert.Equal(t, user.Username, sanitizedUser.Username, "Username should be preserved")
	assert.Equal(t, user.Email, sanitizedUser.Email, "Email should be preserved")
	assert.Equal(t, user.CreatedAt, sanitizedUser.CreatedAt, "CreatedAt should be preserved")
	assert.Equal(t, user.UpdatedAt, sanitizedUser.UpdatedAt, "UpdatedAt should be preserved")
	assert.Equal(t, "", sanitizedUser.PasswordHash, "PasswordHash should be empty in sanitized user")
	assert.Equal(t, "", sanitizedUser.Salt, "Salt should be empty in sanitized user")
}

func TestUserCredentials(t *testing.T) {
	// Create a test credentials with username
	usernameCreds := &models.UserCredentials{
		Username: "testuser",
		Password: "password123",
	}

	// Verify the fields
	assert.Equal(t, "testuser", usernameCreds.Username)
	assert.Equal(t, "", usernameCreds.Email)
	assert.Equal(t, "password123", usernameCreds.Password)

	// Create a test credentials with email
	emailCreds := &models.UserCredentials{
		Email:    "test@example.com",
		Password: "password123",
	}

	// Verify the fields
	assert.Equal(t, "", emailCreds.Username)
	assert.Equal(t, "test@example.com", emailCreds.Email)
	assert.Equal(t, "password123", emailCreds.Password)
}

func TestUserRegistration(t *testing.T) {
	// Create a test registration
	registration := &models.UserRegistration{
		Username:        "newuser",
		Email:           "new@example.com",
		Password:        "password123",
		ConfirmPassword: "password123",
	}

	// Verify the fields
	assert.Equal(t, "newuser", registration.Username)
	assert.Equal(t, "new@example.com", registration.Email)
	assert.Equal(t, "password123", registration.Password)
	assert.Equal(t, "password123", registration.ConfirmPassword)
}

func TestUserUpdate(t *testing.T) {
	// Create a test update with all fields
	fullUpdate := &models.UserUpdate{
		Username: "updateduser",
		Email:    "updated@example.com",
		Password: "newpassword",
	}

	// Verify the fields
	assert.Equal(t, "updateduser", fullUpdate.Username)
	assert.Equal(t, "updated@example.com", fullUpdate.Email)
	assert.Equal(t, "newpassword", fullUpdate.Password)

	// Create a test update with partial fields
	partialUpdate := &models.UserUpdate{
		Username: "updateduser",
	}

	// Verify the fields
	assert.Equal(t, "updateduser", partialUpdate.Username)
	assert.Equal(t, "", partialUpdate.Email)
	assert.Equal(t, "", partialUpdate.Password)
}
