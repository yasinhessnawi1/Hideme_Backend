// Package main is the entry point for the HideMe API Server, which provides
// secure backend services for the HideMe application. This server handles
// authentication, API authorization, and core business logic.
//
// @title HideMe API
// @version 1.0.0
// @description HideMe API Server - User authentication, API authorization, and document processing.
// @termsOfService http://www.hidemeai.com/terms/

// @contact.name API Support
// @contact.url http://www.hidemeai.com/support
// @contact.email support@hidemeai.com

// @license.name Proprietary
// @license.url http://www.hidemeai.com/license

// @host localhost:8080
// @BasePath /api
// @schemes http https

// @securityDefinitions.apikey BearerAuth
// @in header
// @name Authorization
// @description Type "Bearer" followed by a space and the JWT token.

// @securityDefinitions.apikey ApiKeyAuth
// @in header
// @name X-API-Key
// @description API key authentication
package main

import (
	"flag"
	"fmt"
	"github.com/joho/godotenv"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"os"

	_ "github.com/yasinhessnawi1/Hideme_Backend/docs"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/server"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// Version information is set during build time through linker flags.
// These variables provide runtime access to build metadata.
var (
	// version represents the release version of the application.
	version = "dev"

	// commit is the git commit hash from which the application was built.
	commit = "none"

	// buildDate is the timestamp when the application was built.
	buildDate = "unknown"
)

// init loads environment variables from a .env file if present.
// This function executes before main() and sets up initial environment.
func init() {
	// Load .env file if it exists. Not finding a .env file is a non-fatal
	// condition, as configuration might be provided by other means.
	if err := godotenv.Load(); err != nil {
		fmt.Println("Warning: .env file not found or couldn't be loaded")
	}
}

// main is the entry point for the application. It initializes configuration,
// sets up logging, creates and starts the server, and handles graceful shutdown.
// @Description Main function that starts the HideMe API Server
func main() {
	// Define command-line flags for configuration path and version display
	var (
		configPath  string
		showVersion bool
	)

	// Register command-line flags
	flag.StringVar(&configPath, "config", "./configs/config.yaml", "Path to configuration file")
	flag.BoolVar(&showVersion, "version", false, "Show version information")
	flag.Parse()

	// If version flag is set, display build information and exit
	if showVersion {
		fmt.Printf("HideMe API Server\nVersion: %s\nCommit: %s\nBuild Date: %s\n", version, commit, buildDate)
		os.Exit(0)
	}

	// Initialize zerolog with console output format and Unix timestamp format
	zerolog.TimeFieldFormat = zerolog.TimeFormatUnix
	log.Logger = zerolog.New(os.Stdout).With().Timestamp().Logger()

	// Load application configuration from the specified path
	// This includes database settings, JWT configuration, and server options
	cfg, err := config.Load(configPath)
	if err != nil {
		fmt.Printf("Failed to load configuration: %v\n", err)
		os.Exit(1)
	}

	// Override version from build if available (not in dev mode)
	if version != "dev" {
		cfg.App.Version = version
	}

	// Initialize logger with configuration settings
	// This sets log level, output format, and other logging parameters
	utils.InitLogger(cfg)

	// Log startup information for operational visibility
	log.Info().
		Str("version", cfg.App.Version).
		Str("environment", cfg.App.Environment).
		Msg("Starting HideMe API Server")

	// Initialize validator for request payload validation
	utils.InitValidator()

	// Create server instance with loaded configuration
	srv, err := server.NewServer(cfg)
	if err != nil {
		log.Fatal().Err(err).Msg("Failed to create server")
	}

	// Configure periodic tasks like cleanup jobs and health checks
	srv.SetupMaintenanceTasks()

	// Start the server and handle any errors
	// This is a blocking call that runs until termination
	if err := srv.Start(); err != nil {
		log.Fatal().Err(err).Msg("Server error")
	}
}
