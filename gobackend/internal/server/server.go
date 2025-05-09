// Package server provides HTTP server implementation for the HideMe application.
// It handles routing, middleware configuration, and server lifecycle management.
//
// The server package follows a structured initialization approach with dependency injection
// and proper lifecycle management. It handles graceful shutdown, maintenance tasks, and
// GDPR-compliant logging. The server is designed to be secure, maintainable, and resilient,
// with appropriate error handling and recovery mechanisms.
package server

import (
	"context"
	"fmt"
	"github.com/go-chi/chi/v5"
	"github.com/yasinhessnawi1/Hideme_Backend/migrations"
	"github.com/yasinhessnawi1/Hideme_Backend/scripts"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/handlers"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/service"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils/gdprlog"
)

// Handlers contains all HTTP handlers for the application.
// It centralizes handler management for consistent request processing
// and simplifies dependency injection throughout the application.
type Handlers struct {
	// AuthHandler manages authentication-related endpoints
	AuthHandler *handlers.AuthHandler

	// UserHandler manages user profile and account endpoints
	UserHandler *handlers.UserHandler

	// SettingsHandler manages user settings and preferences endpoints
	SettingsHandler *handlers.SettingsHandler

	// DocumentHandler manages document endpoints
	DocumentHandler *handlers.DocumentHandler
}

// AuthProviders contains all authentication providers for the application.
// This structure encapsulates authentication-related dependencies
// to simplify initialization and testing.
type AuthProviders struct {
	// JWTService handles JWT token generation and validation
	JWTService *auth.JWTService

	// PasswordCfg contains password hashing and validation configuration
	PasswordCfg *auth.PasswordConfig
}

// Server represents the API server for the HideMe application.
// It encapsulates all server components and handles server lifecycle management,
// including initialization, startup, and graceful shutdown.
type Server struct {
	// Config contains application configuration
	Config *config.AppConfig

	// Db provides database access
	Db *database.Pool

	// router handles HTTP routing
	router chi.Router

	// Handlers contains all HTTP request handlers
	Handlers *Handlers

	// authProviders contains authentication services
	authProviders *AuthProviders

	// httpServer is the underlying HTTP server
	httpServer *http.Server

	// gdprLogger handles GDPR-compliant logging
	gdprLogger *gdprlog.GDPRLogger
}

// NewServer creates a new server instance with all required components.
// It initializes the database, authentication providers, repositories, services,
// handlers, and GDPR logging, then sets up the HTTP routes.
//
// Parameters:
//   - cfg: Application configuration including database, server, and auth settings
//
// Returns:
//   - A fully initialized Server instance ready to start
//   - An error if initialization of any component fails
//
// The server initialization follows a specific order to ensure proper dependency
// management: database → auth providers → repositories → services → handlers → routes.
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

	// Initialize GDPR logger if not already initialized by utils.InitLogger
	if err := s.setupGDPRLogging(); err != nil {
		log.Warn().Err(err).Msg("Failed to set up GDPR logging, falling back to standard logging")
	}

	// Set up routes
	s.SetupRoutes()

	// Create HTTP server
	s.httpServer = &http.Server{
		Addr:         cfg.Server.ServerAddress(), // This is the fix - using Server settings, not DB
		Handler:      s.router,
		ReadTimeout:  cfg.Server.ReadTimeout,
		WriteTimeout: cfg.Server.WriteTimeout,
		IdleTimeout:  constants.DefaultIdleTimeout,
	}

	return s, nil
}

// setupGDPRLogging initializes GDPR-compliant logging if not already done.
// It creates a logger that separates personal data from regular logs
// and handles proper rotation and retention policies.
//
// Returns:
//   - An error if GDPR logging initialization fails
//
// If a GDPR logger has already been set up through utils.InitLogger,
// this method will use that instance instead of creating a new one.
func (s *Server) setupGDPRLogging() error {
	// Check if we already have a GDPR logger from utils.InitLogger
	if utils.GetGDPRLogger() != nil {
		// Use the existing logger
		s.gdprLogger = utils.GetGDPRLogger()
		return nil
	}

	// Create a new GDPR logger if one doesn't exist
	gdprLogger, err := gdprlog.NewGDPRLogger(&s.Config.GDPRLogging)
	if err != nil {
		return fmt.Errorf("failed to create GDPR logger: %w", err)
	}

	// Set up log rotation
	if err := gdprLogger.SetupLogRotation(); err != nil {
		return fmt.Errorf("failed to set up GDPR log rotation: %w", err)
	}

	// Store the logger
	s.gdprLogger = gdprLogger
	utils.SetGDPRLogger(gdprLogger) // Make it available to utils package

	log.Info().Msg("GDPR logging configured successfully")
	return nil
}

// setupDatabase initializes the database connection and runs migrations.
// It ensures the database schema is up-to-date and seeds initial data if needed.
//
// Returns:
//   - An error if database connection, migration, or seeding fails
//
// This method uses the provided application configuration to establish
// a database connection, then runs migrations to create or update tables
// and seeds initial data like default detection methods.
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

// setupAuthProviders initializes authentication providers.
// It creates services for JWT token management and password handling.
//
// Returns:
//   - An error if auth provider initialization fails
//
// The auth providers include JWT services for token generation and validation,
// and password configuration for secure password hashing and verification.
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

// repositories holds all repositories used by the server.
// These provide data access abstraction for different domain entities.
var repositories struct {
	userRepo        repository.UserRepository
	sessionRepo     repository.SessionRepository
	apiKeyRepo      repository.APIKeyRepository
	settingsRepo    repository.SettingsRepository
	banListRepo     repository.BanListRepository
	patternRepo     repository.PatternRepository
	modelEntityRepo repository.ModelEntityRepository
}

// setupRepositories initializes all data repositories.
// It creates repository instances for each domain entity using the database connection.
//
// Returns:
//   - An error if repository initialization fails
//
// Repositories provide a data access layer that abstracts database operations
// and implements business logic for data validation and transformation.
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

// services holds all services used by the server.
// These provide business logic implementations for the application.
var services struct {
	authService     *service.AuthService
	userService     *service.UserService
	settingsService *service.SettingsService
	dbService       *service.DatabaseService
}

// setupServices initializes all business services.
// It creates service instances using the previously initialized repositories.
//
// Returns:
//   - An error if service initialization fails or required dependencies are missing
//
// Services implement business logic and orchestrate operations across multiple
// repositories, providing a higher-level API for the application handlers.
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

// setupHandlers initializes all HTTP request handlers.
// It creates handler instances using the previously initialized services.
//
// Returns:
//   - An error if handler initialization fails or required services are missing
//
// Handlers process HTTP requests, invoking the appropriate services to
// fulfill each request and formatting the responses for clients.
func (s *Server) setupHandlers() error {
	// Initialize handlers with proper dependency injection
	s.Handlers = &Handlers{
		AuthHandler: handlers.NewAuthHandler(services.authService, s.authProviders.JWTService),
		UserHandler: handlers.NewUserHandler(services.userService),
		// services.settingsService implicitly implements handlers.SettingsServiceInterface
		SettingsHandler: handlers.NewSettingsHandler(services.settingsService),
		DocumentHandler: handlers.NewDocumentHandler(nil), // TODO: wire real service
	}

	// Validate that services are properly initialized
	if s.Handlers.AuthHandler == nil {
		return fmt.Errorf("failed to initialize AuthHandler")
	}

	return nil
}

// Start starts the HTTP server and sets up signal handling for graceful shutdown.
// It runs in a blocking mode, waiting for either server errors or shutdown signals.
//
// Returns:
//   - An error if the server fails to start or encounters an error during operation
//
// This method performs the following operations:
// 1. Starts the HTTP server in a separate goroutine
// 2. Sets up signal handling for graceful shutdown (SIGINT, SIGTERM)
// 3. Initializes periodic maintenance tasks
// 4. Blocks until an error occurs or a shutdown signal is received
// 5. Performs graceful shutdown when requested
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

	// Set up maintenance tasks
	s.SetupMaintenanceTasks()

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

// Shutdown gracefully shuts down the server, closing all connections properly.
// It ensures in-flight requests are completed before shutting down.
//
// Parameters:
//   - ctx: Context with timeout for the shutdown operation
//
// Returns:
//   - An error if shutdown fails within the context timeout
//
// This method performs the following cleanup operations:
// 1. Gracefully shuts down the HTTP server, waiting for in-flight requests
// 2. Closes the database connection
// 3. Performs GDPR log cleanup if needed
func (s *Server) Shutdown(ctx context.Context) error {
	// Shutdown the HTTP server
	if err := s.httpServer.Shutdown(ctx); err != nil {
		return fmt.Errorf("server shutdown error: %w", err)
	}

	log.Info().Msg("Server stopped gracefully")

	// Close the database connection
	s.Db.Close()
	log.Info().Msg("Database connection closed")

	// Clean up any GDPR logging resources if needed
	if s.gdprLogger != nil {
		if err := s.gdprLogger.CleanupLogs(); err != nil {
			log.Warn().Err(err).Msg("Failed to clean up GDPR logs during shutdown")
		}
	}

	return nil
}

// SetupMaintenanceTasks sets up periodic maintenance tasks for the server.
// It creates background goroutines to perform cleanup operations at regular intervals.
//
// These maintenance tasks include:
// 1. Cleaning up expired sessions to prevent database bloat
// 2. Cleaning up expired API keys for security and performance
// 3. Rotating and cleaning up GDPR logs according to retention policies
//
// The tasks run on a fixed schedule defined by constants.DBMaintenanceInterval.
// Each task has its own timeout to prevent long-running operations from blocking others.
func (s *Server) SetupMaintenanceTasks() {
	// Set up a ticker for maintenance tasks
	ticker := time.NewTicker(constants.DBMaintenanceInterval)
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

			// GDPR log rotation and cleanup
			if s.gdprLogger != nil {
				if err := s.gdprLogger.CleanupLogs(); err != nil {
					log.Error().Err(err).Msg("Failed to clean up expired GDPR logs")
				}
			}

			// Call cancel at the end of each iteration to avoid resource leak
			cancel()
		}
	}()
}
