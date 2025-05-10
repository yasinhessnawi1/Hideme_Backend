package service

import (
	"fmt"
	"os"

	"github.com/rs/zerolog/log"
	"github.com/sendgrid/sendgrid-go"
	"github.com/sendgrid/sendgrid-go/helpers/mail"
)

const (
	fromEmailAddress = "support@hidemeai.com"
	fromEmailName    = "HideMe Support"
	frontendResetURL = "https://hidemeai.com/reset-password?token=%s" // Replace with your actual frontend URL
)

// EmailService handles sending emails.
type EmailService struct {
	sendgridAPIKey string
}

// NewEmailService creates a new EmailService.
// It expects the SendGrid API key to be set in the SENDGRID_API_KEY environment variable.
func NewEmailService() (*EmailService, error) {
	apiKey := os.Getenv("SENDGRID_API_KEY")
	if apiKey == "" {
		return nil, fmt.Errorf("SENDGRID_API_KEY environment variable not set")
	}
	return &EmailService{sendgridAPIKey: apiKey}, nil
}

// SendPasswordResetEmail sends a password reset email to the specified user.
func (s *EmailService) SendPasswordResetEmail(toEmail, toName, token string) error {
	from := mail.NewEmail(fromEmailName, fromEmailAddress)
	to := mail.NewEmail(toName, toEmail)
	subject := "Password Reset Request"
	plainTextContent := fmt.Sprintf("Please use the following link to reset your password: %s", fmt.Sprintf(frontendResetURL, token))
	htmlContent := fmt.Sprintf("<strong>Please use the following link to reset your password:</strong> <a href=\"%s\">Reset Password</a>", fmt.Sprintf(frontendResetURL, token))
	message := mail.NewSingleEmail(from, subject, to, plainTextContent, htmlContent)
	client := sendgrid.NewSendClient(s.sendgridAPIKey)
	response, err := client.Send(message)
	if err != nil {
		log.Error().Err(err).Msg("Failed to send password reset email")
		return err
	}
	log.Info().Int("status_code", response.StatusCode).Msg("Password reset email sent")
	return nil
}
