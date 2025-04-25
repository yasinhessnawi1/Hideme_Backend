// Package handlers provides HTTP request handlers for the HideMe API.
// It contains handlers for authentication, user management, settings,
// and generic database operations.
//
// Handlers follow a consistent pattern where they:
// 1. Extract data from the request (URL parameters, body, context)
// 2. Call appropriate service methods to process the request
// 3. Format and return the response
//
// All handlers implement proper error handling and authentication verification where needed.
// Services are injected via interfaces to facilitate unit testing and maintain separation of concerns.
package handlers

import (
	"errors"
	"github.com/go-chi/chi/v5"
	"net/http"
	"strings"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// AuthHandler handles authentication-related routes including
// user registration, login, token management, and API key operations.
// It delegates business logic to the auth service and JWT service.
type AuthHandler struct {
	authService AuthServiceInterface
	jwtService  JWTServiceInterface
}

// NewAuthHandler creates a new AuthHandler with the provided services.
// It performs nil checks on the required services to prevent runtime panics.
//
// Parameters:
//   - authService: Service handling authentication operations
//   - jwtService: Service for JWT token operations
//
// Returns:
//   - A properly initialized AuthHandler
//
// Panics:
//   - If authService or jwtService is nil
func NewAuthHandler(authService AuthServiceInterface, jwtService JWTServiceInterface) *AuthHandler {
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

// Register handles user registration HTTP requests.
// It validates the registration data and creates a new user account.
//
// HTTP Method:
//   - POST
//
// URL Path:
//   - /auth/register
//
// Request Body:
//   - JSON object conforming to models.UserRegistration
//
// Responses:
//   - 201 Created: User created successfully
//   - 400 Bad Request: Invalid request body or validation errors
//   - 409 Conflict: Username or email already exists
//   - 500 Internal Server Error: Server-side error
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
	utils.JSON(w, constants.StatusCreated, user)
}

// Login handles user authentication HTTP requests.
// It validates credentials and issues JWT tokens upon successful authentication.
//
// HTTP Method:
//   - POST
//
// URL Path:
//   - /auth/login
//
// Request Body:
//   - JSON object with "username" or "email" and "password" fields
//
// Responses:
//   - 200 OK: Authentication successful with tokens and user info
//   - 400 Bad Request: Invalid request body
//   - 401 Unauthorized: Invalid credentials
//   - 500 Internal Server Error: Server-side error
//
// Security:
//   - Refresh tokens are stored in HTTP-only cookies for security
//   - Access tokens are returned in the response body
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
	if h.jwtService.GetConfig() == nil {
		utils.InternalServerError(w, errors.New("JWT configuration not initialized"))
		return
	}

	// Set the refresh token as an HTTP-only cookie for security
	// HTTP-only cookies cannot be accessed by JavaScript, protecting against XSS attacks
	refreshExpiry := h.jwtService.GetConfig().RefreshExpiry
	secure := r.TLS != nil || !strings.Contains(h.jwtService.GetConfig().Issuer, "localhost")
	http.SetCookie(w, &http.Cookie{
		Name:     constants.RefreshTokenCookie,
		Value:    refreshToken,
		Path:     "/",
		HttpOnly: true,
		Secure:   secure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   int(refreshExpiry.Seconds()),
		Expires:  time.Now().Add(refreshExpiry),
	})

	// Return the access token and user info
	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"user":         user,
		"access_token": accessToken,
		"token_type":   constants.BearerTokenPrefix[:len(constants.BearerTokenPrefix)-1], // Remove the space
		"expires_in":   int(h.jwtService.GetConfig().Expiry.Seconds()),
	})
}

// RefreshToken handles token refresh HTTP requests.
// It uses the refresh token from the cookie to issue new access and refresh tokens.
//
// HTTP Method:
//   - POST
//
// URL Path:
//   - /auth/refresh
//
// Responses:
//   - 200 OK: Tokens refreshed successfully
//   - 401 Unauthorized: Invalid or missing refresh token
//   - 500 Internal Server Error: Server-side error
//
// Security:
//   - The new refresh token is stored in an HTTP-only cookie
//   - The old refresh token is invalidated to prevent token reuse
func (h *AuthHandler) RefreshToken(w http.ResponseWriter, r *http.Request) {
	// Get the refresh token from the cookie
	cookie, err := r.Cookie(constants.RefreshTokenCookie)
	if err != nil {
		utils.Unauthorized(w, constants.MsgAuthRequired)
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
		Name:     constants.RefreshTokenCookie,
		Value:    newRefreshToken,
		Path:     "/",
		HttpOnly: true,
		Secure:   r.TLS != nil,
		SameSite: http.SameSiteStrictMode,
		MaxAge:   int(refreshExpiry.Seconds()),
		Expires:  time.Now().Add(refreshExpiry),
	})

	// Return the new access token
	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"access_token": accessToken,
		"token_type":   constants.BearerTokenPrefix[:len(constants.BearerTokenPrefix)-1], // Remove the space
		"expires_in":   int(h.jwtService.GetConfig().Expiry.Seconds()),
	})
}

// Logout handles user logout HTTP requests.
// It invalidates the current session and clears the refresh token cookie.
//
// HTTP Method:
//   - POST
//
// URL Path:
//   - /auth/logout
//
// Responses:
//   - 200 OK: Logout successful
//   - 500 Internal Server Error: Server-side error
//
// Security:
//   - The refresh token is invalidated on the server to prevent reuse
//   - The refresh token cookie is cleared from the client
func (h *AuthHandler) Logout(w http.ResponseWriter, r *http.Request) {
	// Get the refresh token from the cookie
	cookie, err := r.Cookie(constants.RefreshTokenCookie)
	if err == nil {
		// Invalidate the session
		_ = h.authService.Logout(r.Context(), cookie.Value)
	}

	// Clear the refresh token cookie
	http.SetCookie(w, &http.Cookie{
		Name:     constants.RefreshTokenCookie,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		Secure:   r.TLS != nil,
		SameSite: http.SameSiteStrictMode,
		MaxAge:   -1,
		Expires:  time.Unix(0, 0),
	})

	// Return success
	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"message": constants.MsgLogoutSuccess,
	})
}

// LogoutAll handles logging out all sessions for a user.
// It invalidates all refresh tokens associated with the user.
//
// HTTP Method:
//   - POST
//
// URL Path:
//   - /auth/logout-all
//
// Requires:
//   - Authentication: User must be logged in
//
// Responses:
//   - 200 OK: All sessions invalidated successfully
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// Security:
//   - All refresh tokens for the user are invalidated on the server
//   - The current refresh token cookie is cleared from the client
func (h *AuthHandler) LogoutAll(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Invalidate all sessions
	if err := h.authService.LogoutAll(r.Context(), userID); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Clear the refresh token cookie
	http.SetCookie(w, &http.Cookie{
		Name:     constants.RefreshTokenCookie,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		Secure:   r.TLS != nil,
		SameSite: http.SameSiteStrictMode,
		MaxAge:   -1,
		Expires:  time.Unix(0, 0),
	})

	// Return success
	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"message": constants.MsgLogoutAllSuccess,
	})
}

// VerifyToken checks if the current token is valid.
// This endpoint is useful for clients to verify authentication status.
//
// HTTP Method:
//   - GET
//
// URL Path:
//   - /auth/verify
//
// Requires:
//   - Authentication: Valid access token
//
// Responses:
//   - 200 OK: Token is valid, with user information
//   - 401 Unauthorized: Token is invalid or expired
func (h *AuthHandler) VerifyToken(w http.ResponseWriter, r *http.Request) {
	// The auth middleware already verified the token
	// Just need to get the user ID and return success
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	username, _ := auth.GetUsername(r)
	email, _ := auth.GetEmail(r)

	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"authenticated": true,
		"user_id":       userID,
		"username":      username,
		"email":         email,
	})
}

// CreateAPIKey handles the creation of a new API key.
// It generates a unique API key associated with the authenticated user.
//
// HTTP Method:
//   - POST
//
// URL Path:
//   - /auth/api-keys
//
// Requires:
//   - Authentication: User must be logged in
//
// Request Body:
//   - JSON object with "name" and "duration" fields
//
// Responses:
//   - 201 Created: API key created successfully
//   - 400 Bad Request: Invalid request body
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// Security:
//   - The raw API key is only returned once upon creation
//   - Subsequent access to the API key will only show a masked version
func (h *AuthHandler) CreateAPIKey(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
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
	utils.JSON(w, constants.StatusCreated, models.APIKeyResponse{
		ID:        apiKey.ID,
		Name:      apiKey.Name,
		Key:       rawKey,
		ExpiresAt: apiKey.ExpiresAt,
		CreatedAt: apiKey.CreatedAt,
	})
}

// ListAPIKeys handles listing all API keys for a user.
//
// HTTP Method:
//   - GET
//
// URL Path:
//   - /auth/api-keys
//
// Requires:
//   - Authentication: User must be logged in
//
// Responses:
//   - 200 OK: List of API keys
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
func (h *AuthHandler) ListAPIKeys(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the API keys
	apiKeys, err := h.authService.ListAPIKeys(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the API keys
	utils.JSON(w, constants.StatusOK, apiKeys)
}

// DeleteAPIKey handles revoking an API key.
//
// HTTP Method:
//   - DELETE
//
// URL Path:
//   - /auth/api-keys/{key_id}
//
// Requires:
//   - Authentication: User must be logged in
//   - URL Parameter: key_id - The ID of the API key to revoke
//
// Responses:
//   - 200 OK: API key revoked successfully
//   - 400 Bad Request: Missing or invalid key_id
//   - 401 Unauthorized: User not authenticated
//   - 404 Not Found: API key not found
//   - 500 Internal Server Error: Server-side error
func (h *AuthHandler) DeleteAPIKey(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the key ID from the URL
	keyID := chi.URLParam(r, constants.ParamKeyID)
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
	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"message": constants.MsgAPIKeyRevoked,
	})
}

// ValidateAPIKey handles validating an API key for external services.
// This endpoint allows verification of API keys without using them directly.
//
// HTTP Method:
//   - GET
//
// URL Path:
//   - /auth/api-keys/validate
//
// Headers:
//   - X-API-Key: The API key to validate
//
// Responses:
//   - 200 OK: API key is valid, with user information
//   - 401 Unauthorized: API key is invalid, expired, or missing
//   - 500 Internal Server Error: Server-side error
func (h *AuthHandler) ValidateAPIKey(w http.ResponseWriter, r *http.Request) {
	// Get the API key from the header
	apiKey := r.Header.Get(constants.HeaderXAPIKey)
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
	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"valid":    true,
		"user_id":  user.ID,
		"username": user.Username,
		"email":    user.Email,
	})
}
