package middleware

import (
	"net/http"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// JWTAuth is a middleware that requires a valid JWT token
func JWTAuth(jwtService auth.JWTValidator) func(http.Handler) http.Handler {
	provider := auth.NewJWTAuthProvider(jwtService)
	return auth.RequireAuth(provider)
}

// APIKeyAuth is a middleware that requires a valid API key
// This will be implemented fully when we have the repository layer
func APIKeyAuth( /* apiKeyRepo repository.APIKeyRepository */ ) func(http.Handler) http.Handler {
	// Simple stub implementation for now
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Get API key from header
			apiKey := r.Header.Get(constants.HeaderXAPIKey)
			if apiKey == "" {
				utils.Unauthorized(w, "API key required")
				return
			}

			// Here we would validate the API key against the database
			// For now, just pass it through as we'll implement this properly later

			next.ServeHTTP(w, r)
		})
	}
}

// RequireRole is a middleware that requires a user to have a specific role
// This will be implemented when we add role-based access control
func RequireRole(role string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Get user ID from context
			userID, ok := auth.GetUserID(r)
			if !ok {
				utils.Unauthorized(w, constants.MsgAuthRequired)
				return
			}

			// Here we would check if the user has the required role
			// For now, just log and pass through
			log.Debug().
				Int64("user_id", userID).
				Str("role", role).
				Msg("Role check would happen here")

			next.ServeHTTP(w, r)
		})
	}
}

// CSRF is a middleware that protects against Cross-Site Request Forgery attacks
func CSRF() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Skip CSRF check for GET, HEAD, OPTIONS, TRACE
			if r.Method == "GET" || r.Method == "HEAD" || r.Method == "OPTIONS" || r.Method == "TRACE" {
				next.ServeHTTP(w, r)
				return
			}

			// Check CSRF token
			csrfToken := r.Header.Get(constants.HeaderXCSRFToken)
			cookie, err := r.Cookie(constants.CSRFTokenCookie)

			if err != nil || cookie.Value == "" || csrfToken == "" || cookie.Value != csrfToken {
				utils.Forbidden(w, "Invalid or missing CSRF token")
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

// RateLimit is a middleware that limits the rate of requests from a single client
// This is a placeholder for a more sophisticated rate limiting implementation
func RateLimit() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Get the client IP
			clientIP := r.RemoteAddr

			// Here we would check if the client has exceeded their rate limit
			// For now, just log and pass through
			log.Debug().
				Str("client_ip", clientIP).
				Msg("Rate limit check would happen here")

			next.ServeHTTP(w, r)
		})
	}
}

// SecurityHeaders adds security-related HTTP headers to responses
func SecurityHeaders() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Add security headers
			w.Header().Set(constants.HeaderXContentTypeOptions, constants.ContentTypeOptionsNoSniff)
			w.Header().Set(constants.HeaderXFrameOptions, constants.FrameOptionsDeny)
			w.Header().Set(constants.HeaderXXSSProtection, constants.XSSProtectionModeBlock)
			w.Header().Set(constants.HeaderReferrerPolicy, constants.ReferrerPolicyStrictOrigin)
			w.Header().Set(constants.HeaderContentSecurityPolicy, constants.CSPDefaultSrc)

			next.ServeHTTP(w, r)
		})
	}
}
