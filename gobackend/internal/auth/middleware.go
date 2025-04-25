// Package auth provides authentication and authorization functionality for the HideMe API.
package auth

import (
	"context"
	"errors"
	"net/http"
	"strings"

	"github.com/google/uuid"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// ContextKey is a custom type for context keys to prevent collisions.
// Using a custom type instead of string or int provides type safety for context values.
type ContextKey string

// Context keys for storing authenticated user information and request metadata.
const (
	// UserIDContextKey is the context key for storing the authenticated user ID.
	UserIDContextKey ContextKey = constants.UserIDContextKey

	// UsernameContextKey is the context key for storing the authenticated username.
	UsernameContextKey ContextKey = constants.UsernameContextKey

	// EmailContextKey is the context key for storing the authenticated user's email.
	EmailContextKey ContextKey = constants.EmailContextKey

	// RequestIDContextKey is the context key for storing the unique request ID.
	RequestIDContextKey ContextKey = constants.RequestIDContextKey
)

// AuthProvider defines methods for different authentication mechanisms.
// This interface allows for pluggable authentication strategies (JWT, API key, etc.).
type AuthProvider interface {
	// Authenticate checks the request and returns user information if valid.
	// It extracts credentials from the request, validates them, and returns
	// identifying information about the authenticated user.
	//
	// Parameters:
	//   - r: The HTTP request containing authentication credentials
	//
	// Returns:
	//   - userID: The authenticated user's ID
	//   - username: The authenticated user's username
	//   - email: The authenticated user's email
	//   - error: An error if authentication fails, nil if successful
	Authenticate(r *http.Request) (int64, string, string, error)
}

// JWTAuthProvider implements JWT-based authentication.
// It extracts and validates JWT tokens from requests to authenticate users.
type JWTAuthProvider struct {
	jwtService JWTValidator
}

// NewJWTAuthProvider creates a new JWTAuthProvider with the specified JWT validator.
//
// Parameters:
//   - jwtService: A service that can validate JWT tokens
//
// Returns:
//   - A properly initialized JWTAuthProvider
func NewJWTAuthProvider(jwtService JWTValidator) *JWTAuthProvider {
	return &JWTAuthProvider{
		jwtService: jwtService,
	}
}

// Authenticate implements the AuthProvider interface for JWT authentication.
// It extracts the JWT token from the Authorization header or a cookie,
// validates it, and returns the authenticated user's information.
//
// Parameters:
//   - r: The HTTP request to authenticate
//
// Returns:
//   - userID: The authenticated user's ID
//   - username: The authenticated user's username
//   - email: The authenticated user's email
//   - error: An error if authentication fails, nil if successful
func (p *JWTAuthProvider) Authenticate(r *http.Request) (int64, string, string, error) {
	// Extract the token from the Authorization header
	authHeader := r.Header.Get(constants.HeaderAuthorization)
	if authHeader == "" {
		// Check for token in cookie as fallback
		cookie, err := r.Cookie(constants.AuthTokenCookie)
		if err != nil {
			return 0, "", "", utils.ErrUnauthorized
		}
		authHeader = constants.BearerTokenPrefix + cookie.Value
	}

	// Check if the header has the correct format (Bearer token)
	if !strings.HasPrefix(authHeader, constants.BearerTokenPrefix) {
		return 0, "", "", utils.ErrUnauthorized
	}

	// Extract the token by removing the "Bearer " prefix
	token := strings.TrimPrefix(authHeader, constants.BearerTokenPrefix)

	// Validate the token and extract claims
	claims, err := p.jwtService.ValidateToken(token, constants.TokenTypeAccess)
	if err != nil {
		return 0, "", "", err
	}

	return claims.UserID, claims.Username, claims.Email, nil
}

// APIKeyAuthProvider implements API key-based authentication.
// NOTE: This is a placeholder for future implementation.
type APIKeyAuthProvider struct {
	// Will be implemented when we have the repository layer
	// apiKeyRepo repository.APIKeyRepository
}

// AuthMiddleware wraps an HTTP handler with authentication.
// It tries each provided authentication provider and only allows the request
// to proceed if at least one authentication method succeeds.
//
// Parameters:
//   - next: The HTTP handler to call if authentication succeeds
//   - providers: One or more authentication providers to try
//
// Returns:
//   - An HTTP handler that enforces authentication
func AuthMiddleware(next http.Handler, providers ...AuthProvider) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Generate a request ID if not already present for request tracking
		requestID := r.Header.Get(constants.HeaderXRequestID)
		if requestID == "" {
			requestID = uuid.New().String()
			r.Header.Set(constants.HeaderXRequestID, requestID)
		}

		// Add request ID to the context
		ctx := context.WithValue(r.Context(), RequestIDContextKey, requestID)

		// Try each authentication provider until one succeeds
		var lastErr error
		for _, provider := range providers {
			userID, username, email, err := provider.Authenticate(r)
			if err == nil {
				// Authentication successful
				// Add user information to the context for use by handlers
				ctx = context.WithValue(ctx, UserIDContextKey, userID)
				ctx = context.WithValue(ctx, UsernameContextKey, username)
				ctx = context.WithValue(ctx, EmailContextKey, email)

				// Log the authentication event
				log.Info().
					Int64("user_id", userID).
					Str("username", username).
					Str("request_id", requestID).
					Str("method", r.Method).
					Str("path", r.URL.Path).
					Msg("User authenticated")

				// Call the next handler with the updated context
				next.ServeHTTP(w, r.WithContext(ctx))
				return
			}
			lastErr = err
		}

		// If we get here, all authentication methods failed
		log.Info().
			Err(lastErr).
			Str("request_id", requestID).
			Str("method", r.Method).
			Str("path", r.URL.Path).
			Msg("Authentication failed")

		// Handle different authentication errors with appropriate responses
		var appErr *utils.AppError
		if errors.As(lastErr, &appErr) {
			utils.ErrorFromAppError(w, appErr)
		} else if errors.Is(lastErr, utils.ErrUnauthorized) {
			utils.Unauthorized(w, constants.MsgAuthRequired)
		} else if errors.Is(lastErr, utils.ErrExpiredToken) {
			utils.Error(w, constants.StatusUnauthorized, constants.CodeTokenExpired, constants.MsgTokenExpired, nil)
		} else {
			utils.Error(w, constants.StatusUnauthorized, constants.CodeAuthenticationFailed, constants.MsgAuthRequired, nil)
		}
	})
}

// RequireAuth is a middleware that requires authentication.
// It returns a middleware function that can be used in HTTP routers.
//
// Parameters:
//   - providers: One or more authentication providers to try
//
// Returns:
//   - A middleware function that requires authentication
func RequireAuth(providers ...AuthProvider) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return AuthMiddleware(next, providers...)
	}
}

// OptionalAuth is a middleware that attempts authentication but continues even if it fails.
// This is useful for routes that can work with or without authentication.
//
// Parameters:
//   - providers: One or more authentication providers to try
//
// Returns:
//   - A middleware function that attempts but doesn't require authentication
func OptionalAuth(providers ...AuthProvider) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Generate a request ID if not already present
			requestID := r.Header.Get(constants.HeaderXRequestID)
			if requestID == "" {
				requestID = uuid.New().String()
				r.Header.Set(constants.HeaderXRequestID, requestID)
			}

			// Add request ID to the context
			ctx := context.WithValue(r.Context(), RequestIDContextKey, requestID)

			// Try each authentication provider, but don't require success
			for _, provider := range providers {
				userID, username, email, err := provider.Authenticate(r)
				if err == nil {
					// Authentication successful, add user info to context
					ctx = context.WithValue(ctx, UserIDContextKey, userID)
					ctx = context.WithValue(ctx, UsernameContextKey, username)
					ctx = context.WithValue(ctx, EmailContextKey, email)

					// Log the authentication event
					log.Info().
						Int64("user_id", userID).
						Str("username", username).
						Str("request_id", requestID).
						Str("method", r.Method).
						Str("path", r.URL.Path).
						Msg("User authenticated (optional)")

					break
				}
			}

			// Call the next handler with the updated context (authenticated or not)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// GetUserID extracts the user ID from the request context.
// It returns the user ID and a boolean indicating if it was found.
//
// Parameters:
//   - r: The HTTP request containing the context
//
// Returns:
//   - The user ID if present
//   - A boolean indicating if the user ID was found
func GetUserID(r *http.Request) (int64, bool) {
	userID, ok := r.Context().Value(UserIDContextKey).(int64)
	return userID, ok
}

// GetUsername extracts the username from the request context.
// It returns the username and a boolean indicating if it was found.
//
// Parameters:
//   - r: The HTTP request containing the context
//
// Returns:
//   - The username if present
//   - A boolean indicating if the username was found
func GetUsername(r *http.Request) (string, bool) {
	username, ok := r.Context().Value(UsernameContextKey).(string)
	return username, ok
}

// GetEmail extracts the email from the request context.
// It returns the email and a boolean indicating if it was found.
//
// Parameters:
//   - r: The HTTP request containing the context
//
// Returns:
//   - The email if present
//   - A boolean indicating if the email was found
func GetEmail(r *http.Request) (string, bool) {
	email, ok := r.Context().Value(EmailContextKey).(string)
	return email, ok
}

// GetRequestID extracts the request ID from the request context.
// It returns the request ID and a boolean indicating if it was found.
//
// Parameters:
//   - r: The HTTP request containing the context
//
// Returns:
//   - The request ID if present
//   - A boolean indicating if the request ID was found
func GetRequestID(r *http.Request) (string, bool) {
	requestID, ok := r.Context().Value(RequestIDContextKey).(string)
	return requestID, ok
}

// IsAuthenticated checks if the request is authenticated.
// It returns true if a user ID is present in the context.
//
// Parameters:
//   - r: The HTTP request to check
//
// Returns:
//   - A boolean indicating if the request is authenticated
func IsAuthenticated(r *http.Request) bool {
	_, ok := GetUserID(r)
	return ok
}
