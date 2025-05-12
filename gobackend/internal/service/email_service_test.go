package service

import (
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
)

// MockSendGridClient is a mock implementation of SendGrid client
type MockSendGridClient struct {
	StatusCode int
	Body       string
	Error      error
	Called     bool
	CalledWith interface{}
}

// Send implements the SendGrid client Send method
func (m *MockSendGridClient) Send(email interface{}) (int, string, error) {
	m.Called = true
	m.CalledWith = email
	return m.StatusCode, m.Body, m.Error
}

// TestNewEmailService tests the NewEmailService function
func TestNewEmailService(t *testing.T) {
	t.Run("Success with API key set", func(t *testing.T) {
		// Arrange
		originalAPIKey := os.Getenv("SENDGRID_API_KEY")
		defer os.Setenv("SENDGRID_API_KEY", originalAPIKey)

		os.Setenv("SENDGRID_API_KEY", "test-api-key")

		// Act
		service, err := NewEmailService()

		// Assert
		assert.NoError(t, err)
		assert.NotNil(t, service)
		assert.Equal(t, "test-api-key", service.sendgridAPIKey)
	})

	t.Run("Error with no API key", func(t *testing.T) {
		// Arrange
		originalAPIKey := os.Getenv("SENDGRID_API_KEY")
		defer os.Setenv("SENDGRID_API_KEY", originalAPIKey)

		os.Setenv("SENDGRID_API_KEY", "")

		// Act
		service, err := NewEmailService()

		// Assert
		assert.Error(t, err)
		assert.Nil(t, service)
		assert.Contains(t, err.Error(), "SENDGRID_API_KEY environment variable not set")
	})
}
