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

// ContextKey is a custom type for context keys to prevent collisions
type ContextKey string

// Context keys
const (
	UserIDContextKey    ContextKey = constants.UserIDContextKey
	UsernameContextKey  ContextKey = constants.UsernameContextKey
	EmailContextKey     ContextKey = constants.EmailContextKey
	RequestIDContextKey ContextKey = constants.RequestIDContextKey
)

/*

// JWTValidator defines the validation method required for JWT auth
type JWTValidator interface {
	ValidateToken(tokenString string, expectedType string) (*CustomClaims, error)
}

*/

// AuthProvider defines methods for different authentication mechanisms
type AuthProvider interface {
	// Authenticate checks the request and returns user information if valid
	Authenticate(r *http.Request) (int64, string, string, error)
}

// JWTAuthProvider implements JWT-based authentication
type JWTAuthProvider struct {
	jwtService JWTValidator
}

// NewJWTAuthProvider creates a new JWTAuthProvider
func NewJWTAuthProvider(jwtService JWTValidator) *JWTAuthProvider {
	return &JWTAuthProvider{
		jwtService: jwtService,
	}
}

// Authenticate implements the AuthProvider interface for JWT
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

	// Check if the header has the correct format
	if !strings.HasPrefix(authHeader, constants.BearerTokenPrefix) {
		return 0, "", "", utils.ErrUnauthorized
	}

	// Extract the token
	token := strings.TrimPrefix(authHeader, constants.BearerTokenPrefix)

	// Validate the token
	claims, err := p.jwtService.ValidateToken(token, constants.TokenTypeAccess)
	if err != nil {
		return 0, "", "", err
	}

	return claims.UserID, claims.Username, claims.Email, nil
}

// APIKeyAuthProvider implements API key-based authentication
type APIKeyAuthProvider struct {
	// Will be implemented when we have the repository layer
	// apiKeyRepo repository.APIKeyRepository
}

// AuthMiddleware wraps an HTTP handler with authentication
func AuthMiddleware(next http.Handler, providers ...AuthProvider) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Generate a request ID if not already present
		requestID := r.Header.Get(constants.HeaderXRequestID)
		if requestID == "" {
			requestID = uuid.New().String()
			r.Header.Set(constants.HeaderXRequestID, requestID)
		}

		// Add request ID to the context
		ctx := context.WithValue(r.Context(), RequestIDContextKey, requestID)

		// Try each authentication provider
		var lastErr error
		for _, provider := range providers {
			userID, username, email, err := provider.Authenticate(r)
			if err == nil {
				// Authentication successful
				// Add user information to the context
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

		// Handle different authentication errors
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

// RequireAuth is a middleware that requires authentication
func RequireAuth(providers ...AuthProvider) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return AuthMiddleware(next, providers...)
	}
}

// OptionalAuth is a middleware that attempts authentication but continues even if it fails
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

			// Try each authentication provider
			for _, provider := range providers {
				userID, username, email, err := provider.Authenticate(r)
				if err == nil {
					// Authentication successful
					// Add user information to the context
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

// GetUserID extracts the user ID from the request context
func GetUserID(r *http.Request) (int64, bool) {
	userID, ok := r.Context().Value(UserIDContextKey).(int64)
	return userID, ok
}

// GetUsername extracts the username from the request context
func GetUsername(r *http.Request) (string, bool) {
	username, ok := r.Context().Value(UsernameContextKey).(string)
	return username, ok
}

// GetEmail extracts the email from the request context
func GetEmail(r *http.Request) (string, bool) {
	email, ok := r.Context().Value(EmailContextKey).(string)
	return email, ok
}

// GetRequestID extracts the request ID from the request context
func GetRequestID(r *http.Request) (string, bool) {
	requestID, ok := r.Context().Value(RequestIDContextKey).(string)
	return requestID, ok
}

// IsAuthenticated checks if the request is authenticated
func IsAuthenticated(r *http.Request) bool {
	_, ok := GetUserID(r)
	return ok
}
