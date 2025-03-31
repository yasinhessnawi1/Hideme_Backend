package server

import (
	"context"
	"fmt"
	"github.com/yasinhessnawi1/Hideme_Backend/migrations"
	"github.com/yasinhessnawi1/Hideme_Backend/scripts"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/handlers"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/service"
)

// Handlers contains all HTTP handlers for the application
type Handlers struct {
	AuthHandler     *handlers.AuthHandler
	UserHandler     *handlers.UserHandler
	SettingsHandler *handlers.SettingsHandler
	GenericHandler  *handlers.GenericHandler
}

// AuthProviders contains all authentication providers for the application
type AuthProviders struct {
	JWTService  *auth.JWTService
	PasswordCfg *auth.PasswordConfig
}

// Server represents the API server
type Server struct {
	Config        *config.AppConfig
	Db            *database.Pool
	router        chi.Router
	Handlers      *Handlers
	authProviders *AuthProviders
	httpServer    *http.Server
}

// NewServer creates a new server instance
func NewServer(cfg *config.AppConfig) (*Server, error) {
	// Create server instance
	s := &Server{
		Config: cfg,
	}

	// Initialize components
	if err := s.setupDatabase(); err != nil {
		return nil, fmt.Errorf("failed to set up database: %w", err)
	}

	if err := s.setupAuthProviders(); err != nil {
		return nil, fmt.Errorf("failed to set up auth providers: %w", err)
	}

	if err := s.setupRepositories(); err != nil {
		return nil, fmt.Errorf("failed to set up repositories: %w", err)
	}

	if err := s.setupServices(); err != nil {
		return nil, fmt.Errorf("failed to set up services: %w", err)
	}

	if err := s.setupHandlers(); err != nil {
		return nil, fmt.Errorf("failed to set up handlers: %w", err)
	}

	// Set up routes
	s.SetupRoutes()

	// Create HTTP server
	s.httpServer = &http.Server{
		Addr:         cfg.Server.ServerAddress(), // This is the fix - using Server settings, not DB
		Handler:      s.router,
		ReadTimeout:  cfg.Server.ReadTimeout,
		WriteTimeout: cfg.Server.WriteTimeout,
		IdleTimeout:  120 * time.Second,
	}

	return s, nil
}

// setupDatabase initializes the database connection
func (s *Server) setupDatabase() error {
	// Connect to the database
	db, err := database.Connect(s.Config)
	if err != nil {
		return err
	}

	s.Db = db

	// Run migrations to create tables if they don't exist
	migrator := migrations.NewMigrator(db)
	if err := migrator.RunMigrations(context.Background()); err != nil {
		return fmt.Errorf("failed to run database migrations: %w", err)
	}

	// Seed initial data
	seeder := scripts.NewSeeder(db)
	if err := seeder.SeedDatabase(context.Background()); err != nil {
		return fmt.Errorf("failed to seed database: %w", err)
	}

	return nil
}

// setupAuthProviders initializes authentication providers
func (s *Server) setupAuthProviders() error {
	// Create JWT service
	jwtService := auth.NewJWTService(&s.Config.JWT)

	// Create password config
	passwordCfg := auth.ConfigFromAppConfig(s.Config)

	// Store providers
	s.authProviders = &AuthProviders{
		JWTService:  jwtService,
		PasswordCfg: passwordCfg,
	}

	return nil
}

// repositories holds all repositories
var repositories struct {
	userRepo        repository.UserRepository
	sessionRepo     repository.SessionRepository
	apiKeyRepo      repository.APIKeyRepository
	settingsRepo    repository.SettingsRepository
	banListRepo     repository.BanListRepository
	patternRepo     repository.PatternRepository
	modelEntityRepo repository.ModelEntityRepository
}

// setupRepositories initializes all repositories
func (s *Server) setupRepositories() error {
	// Initialize repositories
	repositories.userRepo = repository.NewUserRepository(s.Db)
	repositories.sessionRepo = repository.NewSessionRepository(s.Db)
	repositories.apiKeyRepo = repository.NewAPIKeyRepository(s.Db)
	repositories.settingsRepo = repository.NewSettingsRepository(s.Db)
	repositories.banListRepo = repository.NewBanListRepository(s.Db)
	repositories.patternRepo = repository.NewPatternRepository(s.Db)
	repositories.modelEntityRepo = repository.NewModelEntityRepository(s.Db)

	return nil
}

// services holds all services
var services struct {
	authService     *service.AuthService
	userService     *service.UserService
	settingsService *service.SettingsService
	dbService       *service.DatabaseService
}

// setupServices initializes all services
func (s *Server) setupServices() error {
	// Initialize services with explicit error handling
	if s.authProviders == nil || s.authProviders.JWTService == nil {
		return fmt.Errorf("JWT service not initialized")
	}
	if s.authProviders.PasswordCfg == nil {
		return fmt.Errorf("password config not initialized")
	}
	// Initialize services
	services.authService = service.NewAuthService(
		repositories.userRepo,
		repositories.sessionRepo,
		repositories.apiKeyRepo,
		s.authProviders.JWTService,
		s.authProviders.PasswordCfg,
		&s.Config.APIKey,
	)

	services.userService = service.NewUserService(
		repositories.userRepo,
		repositories.sessionRepo,
		repositories.apiKeyRepo,
		s.authProviders.PasswordCfg,
	)

	services.settingsService = service.NewSettingsService(
		repositories.settingsRepo,
		repositories.banListRepo,
		repositories.patternRepo,
		repositories.modelEntityRepo,
	)

	services.dbService = service.NewDatabaseService(s.Db)

	return nil
}

// In internal/server/server.go - setupHandlers method
func (s *Server) setupHandlers() error {
	// Initialize handlers with proper dependency injection
	s.Handlers = &Handlers{
		AuthHandler:     handlers.NewAuthHandler(services.authService, s.authProviders.JWTService),
		UserHandler:     handlers.NewUserHandler(services.userService),
		SettingsHandler: handlers.NewSettingsHandler(services.settingsService),
		GenericHandler:  handlers.NewGenericHandler(services.dbService),
	}

	// Validate that services are properly initialized
	if s.Handlers.AuthHandler == nil {
		return fmt.Errorf("failed to initialize AuthHandler")
	}

	return nil
}

// Start starts the HTTP server
func (s *Server) Start() error {
	// Create a channel to listen for errors from the server
	serverErrors := make(chan error, 1)

	// Start the server in a separate goroutine
	go func() {
		log.Info().
			Str("address", s.Config.Server.ServerAddress()).
			Msg("Starting server")

		serverErrors <- s.httpServer.ListenAndServe()
	}()

	// Create a channel to listen for OS signals
	shutdown := make(chan os.Signal, 1)
	signal.Notify(shutdown, os.Interrupt, syscall.SIGTERM)

	// Block until an OS signal or an error is received
	select {
	case err := <-serverErrors:
		return fmt.Errorf("server error: %w", err)
	case sig := <-shutdown:
		log.Info().
			Str("signal", sig.String()).
			Msg("Shutdown signal received")

		// Create a context with a timeout for graceful shutdown
		ctx, cancel := context.WithTimeout(context.Background(), s.Config.Server.ShutdownTimeout)
		defer cancel()

		// Shutdown the server
		if err := s.Shutdown(ctx); err != nil {
			// Shutdown the server immediately if graceful shutdown fails
			if closeErr := s.httpServer.Close(); closeErr != nil {
				log.Error().Err(closeErr).Msg("failed to close server")
			}
			return fmt.Errorf("could not stop server gracefully: %w", err)
		}
	}

	return nil
}

// Shutdown gracefully shuts down the server
func (s *Server) Shutdown(ctx context.Context) error {
	// Shutdown the HTTP server
	if err := s.httpServer.Shutdown(ctx); err != nil {
		return fmt.Errorf("server shutdown error: %w", err)
	}

	log.Info().Msg("Server stopped gracefully")

	// Close the database connection
	s.Db.Close()
	log.Info().Msg("Database connection closed")

	return nil
}

// SetupMaintenanceTasks sets up periodic maintenance tasks
func (s *Server) SetupMaintenanceTasks() {
	// Set up a ticker for maintenance tasks
	ticker := time.NewTicker(1 * time.Hour)
	go func() {
		for range ticker.C {
			// Create a context with a timeout
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)

			// Cleanup expired sessions
			if count, err := services.authService.CleanupExpiredSessions(ctx); err != nil {
				log.Error().Err(err).Msg("Failed to cleanup expired sessions")
			} else if count > 0 {
				log.Info().Int64("count", count).Msg("Cleaned up expired sessions")
			}

			// Cleanup expired API keys
			if count, err := services.authService.CleanupExpiredAPIKeys(ctx); err != nil {
				log.Error().Err(err).Msg("Failed to cleanup expired API keys")
			} else if count > 0 {
				log.Info().Int64("count", count).Msg("Cleaned up expired API keys")
			}

			// Call cancel at the end of each iteration to avoid resource leak
			cancel()
		}
	}()
}
