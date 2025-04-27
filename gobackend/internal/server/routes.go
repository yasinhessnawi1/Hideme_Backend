// Package server provides HTTP server implementation for the HideMe application.
// It handles routing, middleware configuration, and server lifecycle management.
//
// The package follows a structured approach to route organization, with clear
// grouping based on functionality (auth, users, settings) and proper security
// measures for protected routes. CORS and other security headers are carefully
// configured to provide secure access while enabling legitimate API usage.
package server

import (
	"net/http"
	"os"
	"strings"

	"github.com/go-chi/chi/v5"
	chimiddleware "github.com/go-chi/chi/v5/middleware"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/middleware"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// SetupRoutes configures the routes for the application.
// It creates a router hierarchy with middleware and grouped routes
// according to functionality for organized API structure.
//
// The configured routes include:
// - Health check and version endpoints (unprotected)
// - Authentication endpoints (login, logout, token management)
// - User management endpoints (profile, sessions)
// - API key management
// - Settings management (preferences, ban lists, patterns, entities)
// - Generic database operations (admin/dev access only)
//
// Route protection is handled through middleware for authenticated endpoints.
func (s *Server) SetupRoutes() {
	// Create router
	r := chi.NewRouter()

	// Get allowed origins from environment or use default values
	allowedOrigins := getAllowedOrigins()

	// Custom CORS middleware that applies to all routes
	// This ensures CORS headers are applied properly and consistently
	r.Use(corsMiddleware(allowedOrigins))

	// Base middleware
	r.Use(chimiddleware.RequestID)
	r.Use(middleware.Recovery())
	r.Use(chimiddleware.RealIP)
	r.Use(middleware.SecurityHeaders())

	// Health check and version routes (unprotected)
	r.Group(func(r chi.Router) {
		r.Get("/health", func(w http.ResponseWriter, r *http.Request) {
			// Check database connection
			err := s.Db.HealthCheck(r.Context())
			if err != nil {
				log.Error().Err(err).Msg("Health check failed")
				utils.Error(w, http.StatusServiceUnavailable, "service_unavailable", "Service is not healthy", nil)
				return
			}

			utils.JSON(w, http.StatusOK, map[string]string{
				"status":  "healthy",
				"version": s.Config.App.Version,
			})
		})

		r.Get("/version", func(w http.ResponseWriter, r *http.Request) {
			utils.JSON(w, http.StatusOK, map[string]string{
				"version":     s.Config.App.Version,
				"environment": s.Config.App.Environment,
			})
		})
		// Inside the SetupRoutes function, add this line:
		r.Get("/api/routes", s.GetAPIRoutes)
	})

	// API routes
	r.Route("/api", func(r chi.Router) {
		// Authentication routes
		r.Route("/auth", func(r chi.Router) {
			// Public auth endpoints
			r.Group(func(r chi.Router) {
				r.Post("/signup", s.Handlers.AuthHandler.Register)
				r.Post("/login", s.Handlers.AuthHandler.Login)
				r.Post("/refresh", s.Handlers.AuthHandler.RefreshToken)
				r.Post("/logout", s.Handlers.AuthHandler.Logout)
				r.Post("/validate-key", s.Handlers.AuthHandler.ValidateAPIKey)

				// Explicitly handle OPTIONS preflight request for /verify endpoint
				r.Options("/verify", handlePreflight(allowedOrigins))
				r.Get("/verify", s.Handlers.AuthHandler.VerifyToken)
			})

			// Protected auth endpoints
			r.Group(func(r chi.Router) {
				r.Use(middleware.JWTAuth(s.authProviders.JWTService))
				// verify JWT tokens used for user sessions
				r.Get("/verify", s.Handlers.AuthHandler.VerifyToken)
				// security feature to log out all sessions
				r.Post("/logout-all", s.Handlers.AuthHandler.LogoutAll)
			})
		})

		// User routes (all protected)
		r.Route("/users", func(r chi.Router) {
			// Public user endpoints
			r.Group(func(r chi.Router) {
				r.Use(chimiddleware.NoCache)
				//Checks if a specific username is available (not already taken)
				r.Get("/check/username", s.Handlers.UserHandler.CheckUsername)
				// checks if a specific email address is available (not already registered)
				r.Get("/check/email", s.Handlers.UserHandler.CheckEmail)
			})

			// Protected user endpoints
			r.Group(func(r chi.Router) {
				r.Use(middleware.JWTAuth(s.authProviders.JWTService))

				// /me allows to delete account and change password and get current user info and update user info
				// and get active sessions and invalidate session
				r.Route("/me", func(r chi.Router) {
					r.Get("/", s.Handlers.UserHandler.GetCurrentUser)
					r.Put("/", s.Handlers.UserHandler.UpdateUser)
					r.Delete("/", s.Handlers.UserHandler.DeleteAccount)
					r.Post("/change-password", s.Handlers.UserHandler.ChangePassword)
					r.Get("/sessions", s.Handlers.UserHandler.GetActiveSessions)
					r.Delete("/sessions", s.Handlers.UserHandler.InvalidateSession)
				})
			})
		})

		// API key routes (all protected)
		r.Route("/keys", func(r chi.Router) {
			r.Use(middleware.JWTAuth(s.authProviders.JWTService))

			r.Get("/", s.Handlers.AuthHandler.ListAPIKeys)
			r.Post("/", s.Handlers.AuthHandler.CreateAPIKey)
			r.Delete("/{keyID}", s.Handlers.AuthHandler.DeleteAPIKey)
			r.Get("/{keyID}/decode", s.Handlers.AuthHandler.GetAPIKeyDecoded)
		})

		// Settings routes (all protected)
		r.Route("/settings", func(r chi.Router) {
			r.Use(middleware.JWTAuth(s.authProviders.JWTService))

			r.Get("/", s.Handlers.SettingsHandler.GetSettings)
			r.Put("/", s.Handlers.SettingsHandler.UpdateSettings)

			// Settings export/import routes
			r.Get("/export", s.Handlers.SettingsHandler.ExportSettings)
			r.Post("/import", s.Handlers.SettingsHandler.ImportSettings)

			// Ban list routes
			r.Route("/ban-list", func(r chi.Router) {
				r.Get("/", s.Handlers.SettingsHandler.GetBanList)
				r.Post("/words", s.Handlers.SettingsHandler.AddBanListWords)
				r.Delete("/words", s.Handlers.SettingsHandler.RemoveBanListWords)
			})

			// Search pattern routes
			r.Route("/patterns", func(r chi.Router) {
				r.Get("/", s.Handlers.SettingsHandler.GetSearchPatterns)
				r.Post("/", s.Handlers.SettingsHandler.CreateSearchPattern)
				r.Put("/{patternID}", s.Handlers.SettingsHandler.UpdateSearchPattern)
				r.Delete("/{patternID}", s.Handlers.SettingsHandler.DeleteSearchPattern)
			})

			// Model entity routes
			r.Route("/entities", func(r chi.Router) {
				r.Get("/{methodID}", s.Handlers.SettingsHandler.GetModelEntities)
				r.Post("/", s.Handlers.SettingsHandler.AddModelEntities)
				r.Delete("/{entityID}", s.Handlers.SettingsHandler.DeleteModelEntity)
				r.Delete("/delete_entities_by_method_id/{methodID}", s.Handlers.SettingsHandler.DeleteModelEntityByMethodID)
			})
		})

		// Generic database operations (protected)
		r.Route("/db", func(r chi.Router) {
			r.Use(middleware.JWTAuth(s.authProviders.JWTService))

			r.Get("/{table}", s.Handlers.GenericHandler.GetTableData)
			r.Post("/{table}", s.Handlers.GenericHandler.CreateRecord)
			r.Get("/{table}/{id}", s.Handlers.GenericHandler.GetRecordByID)
			r.Put("/{table}/{id}", s.Handlers.GenericHandler.UpdateRecord)
			r.Delete("/{table}/{id}", s.Handlers.GenericHandler.DeleteRecord)
			r.Get("/{table}/schema", s.Handlers.GenericHandler.GetTableSchema)
		})
	})

	// Set the router
	s.router = r
}

// GetRouter returns the configured router.
//
// Returns:
//   - The chi.Router implementation used by the server
//
// This method is primarily used for testing and for
// integrating the router with other components.
func (s *Server) GetRouter() chi.Router {
	return s.router.(chi.Router)
}

// handlePreflight is an explicit handler for OPTIONS preflight requests.
// It properly configures CORS headers for preflight requests to ensure
// cross-origin requests can proceed if the origin is allowed.
//
// Parameters:
//   - allowedOrigins: A list of origins that are allowed to access the API
//
// Returns:
//   - An http.HandlerFunc that handles the OPTIONS preflight requests
//
// The handler responds with a 204 No Content status, along with appropriate
// CORS headers to allow the specified origins, methods, and headers.
func handlePreflight(allowedOrigins []string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")

		// Check if the origin is allowed
		allowed := false
		for _, allowedOrigin := range allowedOrigins {
			if allowedOrigin == "*" || allowedOrigin == origin {
				allowed = true
				break
			}
		}

		if allowed {
			w.Header().Set(constants.HeaderContentType, constants.ContentTypeJSON)
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers", "Accept, Authorization, Content-Type, X-CSRF-Token, X-Request-ID, X-API-Key")
			w.Header().Set("Access-Control-Allow-Credentials", "true")
			w.Header().Set("Access-Control-Max-Age", "300")
		}

		w.WriteHeader(http.StatusNoContent)
	}
}

// corsMiddleware creates a custom CORS middleware with the specified allowed origins.
// It handles Cross-Origin Resource Sharing to allow browsers to safely access the API
// from different domains while protecting against unauthorized cross-origin requests.
//
// Parameters:
//   - allowedOrigins: A list of origins that are allowed to access the API
//
// Returns:
//   - A middleware function that adds CORS headers to responses
//
// The middleware checks incoming requests against the allowed origins list,
// adds appropriate CORS headers to responses, and handles OPTIONS preflight requests.
// It supports credentials mode for authenticated cross-origin requests.
func corsMiddleware(allowedOrigins []string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			origin := r.Header.Get("Origin")

			// Check if the request's origin is in our allowed list
			for _, allowedOrigin := range allowedOrigins {
				if allowedOrigin == "*" || allowedOrigin == origin {
					// Set CORS headers for all responses, not just OPTIONS
					w.Header().Set("Access-Control-Allow-Origin", origin)

					// These headers are essential for credentials mode
					w.Header().Set("Access-Control-Allow-Credentials", "true")

					// For non-OPTIONS requests, just set these headers and continue
					if r.Method != "OPTIONS" {
						next.ServeHTTP(w, r)
						return
					}

					// Handle OPTIONS preflight requests
					w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
					w.Header().Set("Access-Control-Allow-Headers", "Accept, Authorization, Content-Type, X-CSRF-Token, X-Request-ID, X-API-Key")
					w.Header().Set("Access-Control-Max-Age", "300")

					// Respond to preflight request
					w.WriteHeader(http.StatusNoContent)
					return
				}
			}

			// If origin is not allowed, continue without setting CORS headers
			next.ServeHTTP(w, r)
		})
	}
}

// getAllowedOrigins reads allowed CORS origins from environment variable or falls back to default values.
// This provides flexibility to configure allowed origins without recompiling the application.
//
// Returns:
//   - A slice of strings representing allowed origins for CORS
//
// The function first checks for an ALLOWED_ORIGINS environment variable.
// If set, it splits the value by comma and uses the resulting list.
// Otherwise, it falls back to a default list of origins.
func getAllowedOrigins() []string {
	// Check if ALLOWED_ORIGINS is set in environment
	allowedOriginsEnv := os.Getenv("ALLOWED_ORIGINS")

	// If ALLOWED_ORIGINS is set, use it
	if allowedOriginsEnv != "" {
		// Split by comma and trim spaces
		origins := strings.Split(allowedOriginsEnv, ",")
		for i, origin := range origins {
			origins[i] = strings.TrimSpace(origin)
		}
		log.Info().Strs("allowed_origins", origins).Msg("Using CORS allowed origins from environment")
		return origins
	}

	// Default hardcoded values if environment variable is not set
	// Include both HTTP and HTTPS for localhost to be safe
	defaultOrigins := []string{"https://www.hidemeai.com", "https://hidemeai.com", "http://localhost:5173", "https://localhost:5173"}
	log.Info().Strs("allowed_origins", defaultOrigins).Msg("Using default CORS allowed origins")
	return defaultOrigins
}

// GetAPIRoutes returns documentation about all API routes.
// This provides a self-documenting API endpoint that describes all available endpoints,
// their parameters, expected responses, and required authentication.
//
// Parameters:
//   - w: The HTTP response writer
//   - r: The HTTP request
//
// The function builds a comprehensive map of all API routes organized by category,
// including authentication, user management, API keys, settings, and system endpoints.
// For each endpoint, it provides details about HTTP method, description, required headers,
// request body format, and response format.
func (s *Server) GetAPIRoutes(w http.ResponseWriter, r *http.Request) {
	routes := map[string]interface{}{}

	// Authentication routes
	routes["authentication"] = map[string]interface{}{
		"POST /api/auth/signup": map[string]interface{}{
			"description": "Register a new user",
			"headers": map[string]string{
				"Content-Type": "application/json",
			},
			"body": map[string]interface{}{
				"username":         "string - Unique username",
				"email":            "string - Unique email address",
				"password":         "string - Password (min 8 characters)",
				"confirm_password": "string - Must match password",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"user_id":    1,
					"username":   "johndoe",
					"email":      "john@example.com",
					"created_at": "2023-01-01T12:00:00Z",
					"updated_at": "2023-01-01T12:00:00Z",
				},
			},
		},
		"POST /api/auth/login": map[string]interface{}{
			"description": "Authenticate a user and get access tokens",
			"headers": map[string]string{
				"Content-Type": "application/json",
			},
			"body": map[string]interface{}{
				"username": "string - Username or null if using email",
				"email":    "string - Email or null if using username",
				"password": "string - User's password",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"user": map[string]interface{}{
						"user_id":    1,
						"username":   "johndoe",
						"email":      "john@example.com",
						"created_at": "2023-01-01T12:00:00Z",
						"updated_at": "2023-01-01T12:00:00Z",
					},
					"access_token": "string - JWT access token",
					"token_type":   "Bearer",
					"expires_in":   3600,
				},
			},
			"cookies": map[string]interface{}{
				"refresh_token": "HTTP-only cookie containing the refresh token",
			},
		},
		"POST /api/auth/refresh": map[string]interface{}{
			"description": "Refresh access token using refresh token cookie",
			"headers": map[string]string{
				"Content-Type": "application/json",
			},
			"cookies_required": []string{"refresh_token"},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"access_token": "string - New JWT access token",
					"token_type":   "Bearer",
					"expires_in":   3600,
				},
			},
			"new_cookies": map[string]interface{}{
				"refresh_token": "New HTTP-only cookie with refreshed token",
			},
		},
		"POST /api/auth/logout": map[string]interface{}{
			"description":      "Logout user by invalidating refresh token",
			"cookies_required": []string{"refresh_token"},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"message": "Successfully logged out",
				},
			},
			"cookies_cleared": []string{"refresh_token"},
		},
		"GET /api/auth/verify": map[string]interface{}{
			"description": "Verify current authentication status",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"authenticated": true,
					"user_id":       1,
					"username":      "johndoe",
					"email":         "john@example.com",
				},
			},
		},
		"POST /api/auth/logout-all": map[string]interface{}{
			"description": "Logout from all sessions",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"message": "Successfully logged out of all sessions",
				},
			},
			"cookies_cleared": []string{"refresh_token"},
		},
		"POST /api/auth/validate-key": map[string]interface{}{
			"description": "Validate an API key",
			"headers": map[string]string{
				"X-API-Key": "API key to validate",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"valid":    true,
					"user_id":  1,
					"username": "johndoe",
					"email":    "john@example.com",
				},
			},
		},
	}

	// User routes
	routes["users"] = map[string]interface{}{
		"GET /api/users/check/username": map[string]interface{}{
			"description": "Check if a username is available",
			"query_params": map[string]string{
				"username": "Username to check",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"username":  "johndoe",
					"available": true,
				},
			},
		},
		"GET /api/users/check/email": map[string]interface{}{
			"description": "Check if an email is available",
			"query_params": map[string]string{
				"email": "Email to check",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"email":     "john@example.com",
					"available": true,
				},
			},
		},
		"GET /api/users/me": map[string]interface{}{
			"description": "Get current user profile",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"user_id":    1,
					"username":   "johndoe",
					"email":      "john@example.com",
					"created_at": "2023-01-01T12:00:00Z",
					"updated_at": "2023-01-01T12:00:00Z",
				},
			},
		},
		"PUT /api/users/me": map[string]interface{}{
			"description": "Update current user profile",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
				"Content-Type":  "application/json",
			},
			"body": map[string]interface{}{
				"username": "string (optional) - New username",
				"email":    "string (optional) - New email",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"user_id":    1,
					"username":   "johndoe",
					"email":      "john@example.com",
					"created_at": "2023-01-01T12:00:00Z",
					"updated_at": "2023-01-01T12:00:00Z",
				},
			},
		},
		"DELETE /api/users/me": map[string]interface{}{
			"description": "Delete current user account",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
				"Content-Type":  "application/json",
			},
			"body": map[string]interface{}{
				"password": "string - Current password for verification",
				"confirm":  "string - Must be 'DELETE' to confirm",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"message": "Account successfully deleted",
				},
			},
		},
		"POST /api/users/me/change-password": map[string]interface{}{
			"description": "Change current user password",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
				"Content-Type":  "application/json",
			},
			"body": map[string]interface{}{
				"current_password": "string - Current password",
				"new_password":     "string - New password",
				"confirm_password": "string - Must match new_password",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"message": "Password successfully changed",
				},
			},
		},
		"GET /api/users/me/sessions": map[string]interface{}{
			"description": "Get active sessions for current user",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": []map[string]interface{}{
					{
						"id":         "session-id-1",
						"created_at": "2023-01-01T12:00:00Z",
						"expires_at": "2023-01-08T12:00:00Z",
					},
				},
			},
		},
		"DELETE /api/users/me/sessions": map[string]interface{}{
			"description": "Invalidate a specific session",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
				"Content-Type":  "application/json",
			},
			"body": map[string]interface{}{
				"session_id": "string - ID of the session to invalidate",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"message": "Session successfully invalidated",
				},
			},
		},
	}

	// API Key routes
	routes["api_keys"] = map[string]interface{}{
		"GET /api/keys": map[string]interface{}{
			"description": "List API keys for current user",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": []map[string]interface{}{
					{
						"id":         "key-id-1",
						"name":       "My API Key",
						"expires_at": "2023-12-31T23:59:59Z",
						"created_at": "2023-01-01T12:00:00Z",
					},
				},
			},
		},
		"POST /api/keys": map[string]interface{}{
			"description": "Create a new API key",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
				"Content-Type":  "application/json",
			},
			"body": map[string]interface{}{
				"name":     "string - Name for the API key",
				"duration": "string - Duration (e.g., '30d', '1y')",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"id":         "key-id-1",
					"name":       "My API Key",
					"key":        "actual-api-key-value", // Only returned once on creation
					"expires_at": "2023-12-31T23:59:59Z",
					"created_at": "2023-01-01T12:00:00Z",
				},
			},
		},
		"DELETE /api/keys/{keyID}": map[string]interface{}{
			"description": "Delete an API key",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
			},
			"path_params": map[string]string{
				"keyID": "ID of the API key to delete",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"message": "API key successfully revoked",
				},
			},
		},
	}

	// Settings routes
	routes["settings"] = map[string]interface{}{
		"GET /api/settings": map[string]interface{}{
			"description": "Get user settings",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"setting_id":      1,
					"user_id":         1,
					"remove_images":   false,
					"theme":           "system",
					"auto_processing": true,
					"created_at":      "2023-01-01T12:00:00Z",
					"updated_at":      "2023-01-01T12:00:00Z",
				},
			},
		},
		"PUT /api/settings": map[string]interface{}{
			"description": "Update user settings",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
				"Content-Type":  "application/json",
			},
			"body": map[string]interface{}{
				"remove_images":   "boolean (optional) - Whether to remove images",
				"theme":           "string (optional) - Theme preference (system, light, dark)",
				"auto_processing": "boolean (optional) - Whether to enable auto processing",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"setting_id":      1,
					"user_id":         1,
					"remove_images":   true,
					"theme":           "dark",
					"auto_processing": false,
					"created_at":      "2023-01-01T12:00:00Z",
					"updated_at":      "2023-01-02T12:00:00Z",
				},
			},
		},
		"GET /api/settings/ban-list": map[string]interface{}{
			"description": "Get user's ban list",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"id":    1,
					"words": []string{"word1", "word2", "word3"},
				},
			},
		},
		"POST /api/settings/ban-list/words": map[string]interface{}{
			"description": "Add words to ban list",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
				"Content-Type":  "application/json",
			},
			"body": map[string]interface{}{
				"words": []string{"word4", "word5"},
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"id":    1,
					"words": []string{"word1", "word2", "word3", "word4", "word5"},
				},
			},
		},
		"DELETE /api/settings/ban-list/words": map[string]interface{}{
			"description": "Remove words from ban list",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
				"Content-Type":  "application/json",
			},
			"body": map[string]interface{}{
				"words": []string{"word1", "word2"},
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"id":    1,
					"words": []string{"word3", "word4", "word5"},
				},
			},
		},
		"GET /api/settings/patterns": map[string]interface{}{
			"description": "Get user's search patterns",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": []map[string]interface{}{
					{
						"pattern_id":   1,
						"setting_id":   1,
						"pattern_type": "Normal",
						"pattern_text": "pattern1",
					},
					{
						"pattern_id":   2,
						"setting_id":   1,
						"pattern_type": "case_sensitive",
						"pattern_text": "pattern2",
					},
				},
			},
		},
		"POST /api/settings/patterns": map[string]interface{}{
			"description": "Create a new search pattern",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
				"Content-Type":  "application/json",
			},
			"body": map[string]interface{}{
				"pattern_type": "string - Type of pattern (ai_search, Normal, case_sensitive)",
				"pattern_text": "string - The pattern text",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"pattern_id":   3,
					"setting_id":   1,
					"pattern_type": "ai_search",
					"pattern_text": "new pattern",
				},
			},
		},
		"PUT /api/settings/patterns/{patternID}": map[string]interface{}{
			"description": "Update a search pattern",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
				"Content-Type":  "application/json",
			},
			"path_params": map[string]string{
				"patternID": "ID of the pattern to update",
			},
			"body": map[string]interface{}{
				"pattern_type": "string (optional) - Type of pattern",
				"pattern_text": "string (optional) - The pattern text",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"pattern_id":   3,
					"setting_id":   1,
					"pattern_type": "Normal",
					"pattern_text": "updated pattern",
				},
			},
		},
		"DELETE /api/settings/patterns/{patternID}": map[string]interface{}{
			"description": "Delete a search pattern",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
			},
			"path_params": map[string]string{
				"patternID": "ID of the pattern to delete",
			},
			"response": map[string]interface{}{
				"success":     true,
				"status_code": 204,
				"no_content":  true,
			},
		},
		"GET /api/settings/entities/{methodID}": map[string]interface{}{
			"description": "Get model entities for a specific method",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
			},
			"path_params": map[string]string{
				"methodID": "ID of the detection method",
			},
			"response": map[string]interface{}{
				"success": true,
				"data": []map[string]interface{}{
					{
						"id":          1,
						"setting_id":  1,
						"method_id":   1,
						"entity_text": "Entity 1",
						"method_name": "Method Name",
					},
				},
			},
		},
		"POST /api/settings/entities": map[string]interface{}{
			"description": "Add model entities",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
				"Content-Type":  "application/json",
			},
			"body": map[string]interface{}{
				"method_id":    "number - Detection method ID",
				"entity_texts": []string{"Entity 2", "Entity 3"},
			},
			"response": map[string]interface{}{
				"success": true,
				"data": []map[string]interface{}{
					{
						"id":          2,
						"setting_id":  1,
						"method_id":   1,
						"entity_text": "Entity 2",
					},
					{
						"id":          3,
						"setting_id":  1,
						"method_id":   1,
						"entity_text": "Entity 3",
					},
				},
			},
		},
		"DELETE /api/settings/entities/{entityID}": map[string]interface{}{
			"description": "Delete a model entity",
			"headers": map[string]string{
				"Authorization": "Bearer {access_token}",
			},
			"path_params": map[string]string{
				"entityID": "ID of the entity to delete",
			},
			"response": map[string]interface{}{
				"success":     true,
				"status_code": 204,
				"no_content":  true,
			},
		},
	}

	// System routes
	routes["system"] = map[string]interface{}{
		"GET /health": map[string]interface{}{
			"description": "Health check endpoint",
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"status":  "healthy",
					"version": "1.0.0",
				},
			},
		},
		"GET /version": map[string]interface{}{
			"description": "Get application version",
			"response": map[string]interface{}{
				"success": true,
				"data": map[string]interface{}{
					"version":     "1.0.0",
					"environment": "production",
				},
			},
		},
		"GET /api/routes": map[string]interface{}{
			"description": "Get comprehensive API route documentation",
			"response": map[string]interface{}{
				"success": true,
				"data":    "This document you're viewing right now",
			},
		},
	}

	utils.JSON(w, http.StatusOK, routes)
}
