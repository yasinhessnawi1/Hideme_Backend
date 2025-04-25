// Package middleware provides HTTP middleware components for the HideMe API.
// It includes authentication, authorization, security, and other cross-cutting concerns.
//
// These middleware components can be composed to build secure request processing
// pipelines that handle common concerns like authentication, CSRF protection,
// and security headers.
package middleware

import (
	"net/http"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// JWTAuth is a middleware that requires a valid JWT token for a request to proceed.
// It verifies the token signature, expiration, and that it's an access token.
//
// Parameters:
//   - jwtService: A service that can validate JWT tokens
//
// Returns:
//   - A middleware function that can be used with an HTTP handler
func JWTAuth(jwtService auth.JWTValidator) func(http.Handler) http.Handler {
	provider := auth.NewJWTAuthProvider(jwtService)
	return auth.RequireAuth(provider)
}

// APIKeyAuth is a middleware that requires a valid API key for a request to proceed.
// This is a placeholder implementation that will be completed when the repository layer is available.
//
// Returns:
//   - A middleware function that can be used with an HTTP handler
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

// RequireRole is a middleware that requires a user to have a specific role.
// This is a placeholder implementation that will be completed when role-based access control is added.
//
// Parameters:
//   - role: The role that a user must have to access the endpoint
//
// Returns:
//   - A middleware function that can be used with an HTTP handler
func RequireRole(role string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Get user ID from context (must be authenticated)
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

// CSRF is a middleware that protects against Cross-Site Request Forgery attacks.
// It verifies that the CSRF token in the request header matches the token in the cookie.
//
// Returns:
//   - A middleware function that can be used with an HTTP handler
func CSRF() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Skip CSRF check for safe methods (GET, HEAD, OPTIONS, TRACE)
			// These methods are safe because they should not modify state
			if r.Method == "GET" || r.Method == "HEAD" || r.Method == "OPTIONS" || r.Method == "TRACE" {
				next.ServeHTTP(w, r)
				return
			}

			// Check CSRF token from header against the token in the cookie
			csrfToken := r.Header.Get(constants.HeaderXCSRFToken)
			cookie, err := r.Cookie(constants.CSRFTokenCookie)

			// Verify that both tokens exist and match
			if err != nil || cookie.Value == "" || csrfToken == "" || cookie.Value != csrfToken {
				utils.Forbidden(w, "Invalid or missing CSRF token")
				return
			}

			next.ServeHTTP(w, r)
		})
	}
}

// RateLimit is a middleware that limits the rate of requests from a single client.
// This is a placeholder implementation that will be replaced with a more sophisticated rate limiting solution.
//
// Returns:
//   - A middleware function that can be used with an HTTP handler
func RateLimit() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Get the client IP address
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

// SecurityHeaders adds security-related HTTP headers to responses.
// These headers help protect against common web vulnerabilities.
//
// Returns:
//   - A middleware function that can be used with an HTTP handler
func SecurityHeaders() func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Add security headers

			// X-Content-Type-Options: Prevents MIME type sniffing
			w.Header().Set(constants.HeaderXContentTypeOptions, constants.ContentTypeOptionsNoSniff)

			// X-Frame-Options: Prevents clickjacking via iframes
			w.Header().Set(constants.HeaderXFrameOptions, constants.FrameOptionsDeny)

			// X-XSS-Protection: Enables browser XSS filtering
			w.Header().Set(constants.HeaderXXSSProtection, constants.XSSProtectionModeBlock)

			// Referrer-Policy: Controls how much referrer information is sent
			w.Header().Set(constants.HeaderReferrerPolicy, constants.ReferrerPolicyStrictOrigin)

			// Content-Security-Policy: Restricts resource loading to prevent XSS and data injection
			w.Header().Set(constants.HeaderContentSecurityPolicy, constants.CSPDefaultSrc)

			next.ServeHTTP(w, r)
		})
	}
}
