package server

import (
	"net/http"

	"github.com/go-chi/chi/v5"
	chimiddleware "github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/middleware"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// SetupRoutes configures the routes for the application
func (s *Server) SetupRoutes() {
	// Create router
	r := chi.NewRouter()

	// Base middleware
	r.Use(chimiddleware.RequestID)
	r.Use(middleware.Recovery())
	r.Use(chimiddleware.RealIP)
	r.Use(middleware.SecurityHeaders())

	// CORS configuration
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   s.Config.CORS.AllowedOrigins,
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID", "X-API-Key"},
		ExposedHeaders:   []string{"Link", "X-Request-ID"},
		AllowCredentials: s.Config.CORS.AllowCredentials,
		MaxAge:           300, // Maximum value not caught in preflight requests
	}))

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
		})

		// Settings routes (all protected)
		r.Route("/settings", func(r chi.Router) {
			r.Use(middleware.JWTAuth(s.authProviders.JWTService))

			r.Get("/", s.Handlers.SettingsHandler.GetSettings)
			r.Put("/", s.Handlers.SettingsHandler.UpdateSettings)

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

// GetRouter returns the configured router
func (s *Server) GetRouter() chi.Router {
	return s.router.(chi.Router)
}
