package handlers

import (
	"errors"
	"github.com/go-chi/chi/v5"
	"net/http"
	"strings"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/service"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// AuthHandler handles authentication-related routes
type AuthHandler struct {
	authService *service.AuthService
	jwtService  *auth.JWTService
}

// NewAuthHandler creates a new AuthHandler
func NewAuthHandler(authService *service.AuthService, jwtService *auth.JWTService) *AuthHandler {
	if authService == nil {
		panic("authService cannot be nil")
	}
	if jwtService == nil {
		panic("jwtService cannot be nil")
	}
	return &AuthHandler{
		authService: authService,
		jwtService:  jwtService,
	}
}

// Register handles user registration
func (h *AuthHandler) Register(w http.ResponseWriter, r *http.Request) {
	// Decode and validate the request body
	var reg models.UserRegistration
	if err := utils.DecodeAndValidate(r, &reg); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Register the user
	user, err := h.authService.RegisterUser(r.Context(), &reg)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the newly created user
	utils.JSON(w, http.StatusCreated, user)
}

// Login handles user authentication
func (h *AuthHandler) Login(w http.ResponseWriter, r *http.Request) {
	// Defensive programming - check for nil services
	if h.authService == nil {
		utils.InternalServerError(w, errors.New("auth service not initialized"))
		return
	}

	if h.jwtService == nil {
		utils.InternalServerError(w, errors.New("JWT service not initialized"))
		return
	}

	// Decode and validate the request body
	var creds models.UserCredentials
	if err := utils.DecodeAndValidate(r, &creds); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Authenticate the user
	user, accessToken, refreshToken, err := h.authService.AuthenticateUser(r.Context(), &creds)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Ensure we have a valid configuration
	if h.jwtService.Config == nil {
		utils.InternalServerError(w, errors.New("JWT configuration not initialized"))
		return
	}

	// Set the refresh token as an HTTP-only cookie
	refreshExpiry := h.jwtService.Config.RefreshExpiry
	secure := r.TLS != nil || !strings.Contains(h.jwtService.Config.Issuer, "localhost")
	http.SetCookie(w, &http.Cookie{
		Name:     "refresh_token",
		Value:    refreshToken,
		Path:     "/",
		HttpOnly: true,
		Secure:   secure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   int(refreshExpiry.Seconds()),
		Expires:  time.Now().Add(refreshExpiry),
	})

	// Return the access token and user info
	utils.JSON(w, http.StatusOK, map[string]interface{}{
		"user":         user,
		"access_token": accessToken,
		"token_type":   "Bearer",
		"expires_in":   int(h.jwtService.Config.Expiry.Seconds()),
	})
}

// RefreshToken handles token refresh
func (h *AuthHandler) RefreshToken(w http.ResponseWriter, r *http.Request) {
	// Get the refresh token from the cookie
	cookie, err := r.Cookie("refresh_token")
	if err != nil {
		utils.Unauthorized(w, "Refresh token not found")
		return
	}

	// Refresh the tokens
	accessToken, newRefreshToken, err := h.authService.RefreshTokens(r.Context(), cookie.Value)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Set the new refresh token as a cookie
	refreshExpiry := h.jwtService.GetConfig().RefreshExpiry
	http.SetCookie(w, &http.Cookie{
		Name:     "refresh_token",
		Value:    newRefreshToken,
		Path:     "/",
		HttpOnly: true,
		Secure:   r.TLS != nil,
		SameSite: http.SameSiteStrictMode,
		MaxAge:   int(refreshExpiry.Seconds()),
		Expires:  time.Now().Add(refreshExpiry),
	})

	// Return the new access token
	utils.JSON(w, http.StatusOK, map[string]interface{}{
		"access_token": accessToken,
		"token_type":   "Bearer",
		"expires_in":   int(h.jwtService.GetConfig().Expiry.Seconds()),
	})
}

// Logout handles user logout
func (h *AuthHandler) Logout(w http.ResponseWriter, r *http.Request) {
	// Get the refresh token from the cookie
	cookie, err := r.Cookie("refresh_token")
	if err == nil {
		// Invalidate the session
		_ = h.authService.Logout(r.Context(), cookie.Value)
	}

	// Clear the refresh token cookie
	http.SetCookie(w, &http.Cookie{
		Name:     "refresh_token",
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		Secure:   r.TLS != nil,
		SameSite: http.SameSiteStrictMode,
		MaxAge:   -1,
		Expires:  time.Unix(0, 0),
	})

	// Return success
	utils.JSON(w, http.StatusOK, map[string]interface{}{
		"message": "Successfully logged out",
	})
}

// LogoutAll handles logging out all sessions for a user
func (h *AuthHandler) LogoutAll(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Invalidate all sessions
	if err := h.authService.LogoutAll(r.Context(), userID); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Clear the refresh token cookie
	http.SetCookie(w, &http.Cookie{
		Name:     "refresh_token",
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		Secure:   r.TLS != nil,
		SameSite: http.SameSiteStrictMode,
		MaxAge:   -1,
		Expires:  time.Unix(0, 0),
	})

	// Return success
	utils.JSON(w, http.StatusOK, map[string]interface{}{
		"message": "Successfully logged out of all sessions",
	})
}

// VerifyToken checks if the current token is valid
func (h *AuthHandler) VerifyToken(w http.ResponseWriter, r *http.Request) {
	// The auth middleware already verified the token
	// Just need to get the user ID and return success
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	username, _ := auth.GetUsername(r)
	email, _ := auth.GetEmail(r)

	utils.JSON(w, http.StatusOK, map[string]interface{}{
		"authenticated": true,
		"user_id":       userID,
		"username":      username,
		"email":         email,
	})
}

// CreateAPIKey handles the creation of a new API key
func (h *AuthHandler) CreateAPIKey(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Decode and validate the request body
	var req models.APIKeyCreationRequest
	if err := utils.DecodeAndValidate(r, &req); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Parse the duration
	duration, err := auth.ParseDuration(req.Duration)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Create the API key
	rawKey, apiKey, err := h.authService.CreateAPIKey(r.Context(), userID, req.Name, duration)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the API key
	utils.JSON(w, http.StatusCreated, models.APIKeyResponse{
		ID:        apiKey.ID,
		Name:      apiKey.Name,
		Key:       rawKey,
		ExpiresAt: apiKey.ExpiresAt,
		CreatedAt: apiKey.CreatedAt,
	})
}

// ListAPIKeys handles listing all API keys for a user
func (h *AuthHandler) ListAPIKeys(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Get the API keys
	apiKeys, err := h.authService.ListAPIKeys(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the API keys
	utils.JSON(w, http.StatusOK, apiKeys)
}

// DeleteAPIKey handles revoking an API key
func (h *AuthHandler) DeleteAPIKey(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	//TODO check key_id
	// Get the key ID from the URL
	keyID := chi.URLParam(r, "keyID")
	if keyID == "" {
		utils.BadRequest(w, "key_id parameter is required", nil)
		return
	}

	// Delete the API key
	if err := h.authService.DeleteAPIKey(r.Context(), userID, keyID); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return success
	utils.JSON(w, http.StatusOK, map[string]interface{}{
		"message": "API key successfully revoked",
	})
}

// ValidateAPIKey handles validating an API key for external services
func (h *AuthHandler) ValidateAPIKey(w http.ResponseWriter, r *http.Request) {
	// Get the API key from the header
	apiKey := r.Header.Get("X-API-Key")
	if apiKey == "" {
		utils.Unauthorized(w, "API key required")
		return
	}

	// Verify the API key
	user, err := h.authService.VerifyAPIKey(r.Context(), apiKey)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the user info
	utils.JSON(w, http.StatusOK, map[string]interface{}{
		"valid":    true,
		"user_id":  user.ID,
		"username": user.Username,
		"email":    user.Email,
	})
}
