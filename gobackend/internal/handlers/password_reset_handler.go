package handlers

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth" // Assuming auth.HashPassword, auth.PasswordConfig are here
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/service"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils" // Assuming utils.DecodeAndValidate, utils.JSON, utils.JSON, utils.IsValidEmail
)

const (
	PasswordResetTokenDuration = 1 * time.Hour // Token validity duration
)

// PasswordResetHandler holds dependencies for password reset operations.
// You will need to initialize these dependencies (e.g., in your main.go or server setup)
// and pass them to the handler functions, perhaps by making them methods on this struct.
// For simplicity here, I'm assuming they are accessible globally or passed directly.
// A better approach is dependency injection.
type PasswordResetHandler struct {
	UserRepo          repository.UserRepository // Define this interface for your user repo
	PasswordResetRepo *repository.PasswordResetRepository
	EmailService      *service.EmailService
	PasswordConfig    *auth.PasswordConfig // Assuming this is needed for HashPassword
}

// NewPasswordResetHandler creates a new PasswordResetHandler with its dependencies.
func NewPasswordResetHandler(userRepo repository.UserRepository, prRepo *repository.PasswordResetRepository, emailService *service.EmailService, pwConfig *auth.PasswordConfig) *PasswordResetHandler {
	return &PasswordResetHandler{
		UserRepo:          userRepo,
		PasswordResetRepo: prRepo,
		EmailService:      emailService,
		PasswordConfig:    pwConfig,
	}
}

// ForgotPassword handles the request to initiate a password reset.
func (h *PasswordResetHandler) ForgotPassword(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req models.ForgotPasswordRequest

	if err := utils.DecodeAndValidate(r, &req); err != nil {
		utils.JSON(w, http.StatusBadRequest, err.Error()) // Or use your specific error handling
		return
	}

	// Always respond with this message for security
	genericMsg := map[string]string{"message": "If an account with that email exists, a password reset link has been sent."}

	user, err := h.UserRepo.GetByEmail(ctx, req.Email)
	if err != nil {
		// Log the error for internal monitoring
		log.Warn().Err(err).Str("email", req.Email).Msg("Password reset requested for non-existent or error user")
		utils.JSON(w, http.StatusOK, genericMsg)
		return
	}

	plainToken, tokenHash, err := repository.GenerateToken()
	if err != nil {
		log.Error().Err(err).Msg("Failed to generate password reset token")
		utils.JSON(w, http.StatusOK, genericMsg)
		return
	}

	if err := h.PasswordResetRepo.Create(ctx, user.ID, tokenHash, PasswordResetTokenDuration); err != nil {
		log.Error().Err(err).Int64("user_id", user.ID).Msg("Failed to store password reset token")
		utils.JSON(w, http.StatusOK, genericMsg)
		return
	}

	err = h.EmailService.SendPasswordResetEmail(user.Email, user.Username, plainToken)
	if err != nil {
		log.Error().Err(err).Str("email", user.Email).Msg("Failed to send password reset email")
		utils.JSON(w, http.StatusOK, genericMsg)
		return
	}

	utils.JSON(w, http.StatusOK, genericMsg)
}

// ResetPassword handles the request to reset a password using a token.
func (h *PasswordResetHandler) ResetPassword(w http.ResponseWriter, r *http.Request) {
	ctx := r.Context()
	var req models.ResetPasswordRequest

	if err := utils.DecodeAndValidate(r, &req); err != nil {
		utils.JSON(w, http.StatusBadRequest, err.Error()) // Or use your specific error handling
		return
	}

	// Validate password strength (utils.ValidatePassword or auth.ValidateStrongPassword)
	// Example: using utils.ValidatePassword, assuming it exists and fits your needs
	if err := utils.ValidatePassword(req.NewPassword); err != nil { // Ensure this function exists and is suitable
		utils.JSON(w, http.StatusBadRequest, err.Error())
		return
	}

	// Hash the received plain token to look it up in the DB
	hash := sha256.Sum256([]byte(req.Token))
	tokenHashToValidate := hex.EncodeToString(hash[:])

	userID, expiresAt, err := h.PasswordResetRepo.GetUserIDByTokenHash(ctx, tokenHashToValidate)
	if err != nil {
		if errors.Is(err, repository.ErrTokenNotFound) {
			utils.JSON(w, http.StatusBadRequest, "Invalid or expired password reset token.")
			return
		}
		log.Error().Err(err).Msg("Failed to validate password reset token")
		utils.JSON(w, http.StatusInternalServerError, "Error validating reset token.")
		return
	}

	if time.Now().After(expiresAt) {
		// Attempt to delete the expired token
		if delErr := h.PasswordResetRepo.Delete(ctx, tokenHashToValidate); delErr != nil {
			log.Error().Err(delErr).Str("token_hash", tokenHashToValidate).Msg("Failed to delete expired token")
		}
		utils.JSON(w, http.StatusBadRequest, "Password reset token has expired.")
		return
	}

	// Hash the new password
	// Assuming your auth.HashPassword takes (password string, cfg *PasswordConfig)
	// and returns (hashedPassword string, salt string, error)
	newPasswordHash, newSalt, err := auth.HashPassword(req.NewPassword, h.PasswordConfig)
	if err != nil {
		log.Error().Err(err).Msg("Failed to hash new password")
		utils.JSON(w, http.StatusInternalServerError, "Error processing new password.")
		return
	}

	// Update password in user repository
	// Assuming your userRepo.ChangePassword takes (ctx, id, passwordHash, salt)
	if err := h.UserRepo.ChangePassword(ctx, userID, newPasswordHash, newSalt); err != nil {
		log.Error().Err(err).Int64("user_id", userID).Msg("Failed to change password in repository")
		utils.JSON(w, http.StatusInternalServerError, "Could not update password.")
		return
	}

	// Password changed successfully, delete the reset token
	if err := h.PasswordResetRepo.Delete(ctx, tokenHashToValidate); err != nil {
		log.Error().Err(err).Str("token_hash", tokenHashToValidate).Msg("Failed to delete used password reset token")
		// Continue, as password was successfully changed. This is a cleanup step.
	}

	// Optionally, delete all tokens for this user to invalidate any other pending requests
	if err := h.PasswordResetRepo.DeleteByUserID(ctx, userID); err != nil {
		log.Error().Err(err).Int64("user_id", userID).Msg("Failed to delete all password reset tokens for user")
		// This is a cleanup step, do not fail the request if this errors out.
	}

	utils.JSON(w, http.StatusOK, map[string]string{"message": "Password has been reset successfully."})
}
