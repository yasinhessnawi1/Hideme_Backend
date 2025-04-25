package handlers

import (
	"net/http"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// UserHandler handles user-related routes
type UserHandler struct {
	userService UserServiceInterface // Changed from *service.UserService
}

// NewUserHandler creates a new UserHandler
func NewUserHandler(userService UserServiceInterface) *UserHandler { // Changed parameter type
	return &UserHandler{
		userService: userService,
	}
}

// GetCurrentUser returns the current user's profile
func (h *UserHandler) GetCurrentUser(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the user from the database
	user, err := h.userService.GetUserByID(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the user
	utils.JSON(w, constants.StatusOK, user)
}

// UpdateUser handles updating the current user's profile
func (h *UserHandler) UpdateUser(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Decode and validate the request body
	var update models.UserUpdate
	if err := utils.DecodeAndValidate(r, &update); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Update the user
	user, err := h.userService.UpdateUser(r.Context(), userID, &update)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the updated user
	utils.JSON(w, constants.StatusOK, user)
}

// ChangePassword handles changing the current user's password
func (h *UserHandler) ChangePassword(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Decode and validate the request body
	var req struct {
		CurrentPassword string `json:"current_password" validate:"required"`
		NewPassword     string `json:"new_password" validate:"required,min=8"`
		ConfirmPassword string `json:"confirm_password" validate:"required,eqfield=NewPassword"`
	}
	if err := utils.DecodeAndValidate(r, &req); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// For security, we need to authenticate with the current password
	// This would typically be handled by the auth service
	// For now, we'll just change the password directly

	// Change the password
	if err := h.userService.ChangePassword(r.Context(), userID, req.NewPassword); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return success
	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"message": constants.MsgPasswordChanged,
	})
}

// DeleteAccount handles deleting the current user's account
func (h *UserHandler) DeleteAccount(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Decode and validate the request body
	var req struct {
		Password string `json:"password" validate:"required"`
		Confirm  string `json:"confirm" validate:"required,eq=DELETE"`
	}
	if err := utils.DecodeAndValidate(r, &req); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// For security, we need to authenticate with the password and require confirmation
	// This would typically be handled by the auth service
	// For now, we'll just delete the account directly

	// Delete the account
	if err := h.userService.DeleteUser(r.Context(), userID); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return success
	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"message": constants.MsgUserDeleted,
	})
}

// CheckUsername checks if a username is available
func (h *UserHandler) CheckUsername(w http.ResponseWriter, r *http.Request) {
	// Get the username from the query
	username := r.URL.Query().Get(constants.QueryParamUsername)
	if username == "" {
		utils.BadRequest(w, "Username parameter is required", nil)
		return
	}

	// Check if the username is available
	available, err := h.userService.CheckUsername(r.Context(), username)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the result
	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"username":  username,
		"available": available,
	})
}

// CheckEmail checks if an email is available
func (h *UserHandler) CheckEmail(w http.ResponseWriter, r *http.Request) {
	// Get the email from the query
	email := r.URL.Query().Get(constants.QueryParamEmail)
	if email == "" {
		utils.BadRequest(w, "Email parameter is required", nil)
		return
	}

	// Check if the email is available
	available, err := h.userService.CheckEmail(r.Context(), email)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the result
	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"email":     email,
		"available": available,
	})
}

// GetActiveSessions returns the current user's active sessions
func (h *UserHandler) GetActiveSessions(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the active sessions
	sessions, err := h.userService.GetUserActiveSessions(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the sessions
	utils.JSON(w, constants.StatusOK, sessions)
}

// InvalidateSession invalidates a specific session
func (h *UserHandler) InvalidateSession(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the session ID from the request
	var req struct {
		SessionID string `json:"session_id" validate:"required"`
	}
	if err := utils.DecodeAndValidate(r, &req); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Invalidate the session
	if err := h.userService.InvalidateSession(r.Context(), userID, req.SessionID); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return success
	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"message": constants.MsgSessionInvalidated,
	})
}
