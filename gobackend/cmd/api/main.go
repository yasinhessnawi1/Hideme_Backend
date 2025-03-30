package main

import (
	"flag"
	"fmt"
	"github.com/joho/godotenv"
	"github.com/rs/zerolog"
	"github.com/rs/zerolog/log"
	"os"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/server"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// Version information (set during build)
var (
	version   = "dev"
	commit    = "none"
	buildDate = "unknown"
)

func init() {
	// Load .env file if it exists
	if err := godotenv.Load(); err != nil {
		fmt.Println("Warning: .env file not found or couldn't be loaded")
	}
}

func main() {
	// Define command-line flags
	var (
		configPath  string
		showVersion bool
	)

	flag.StringVar(&configPath, "config", "./configs/config.yaml", "Path to configuration file")
	flag.BoolVar(&showVersion, "version", false, "Show version information")
	flag.Parse()

	// Show version information and exit if requested
	if showVersion {
		fmt.Printf("HideMe API Server\nVersion: %s\nCommit: %s\nBuild Date: %s\n", version, commit, buildDate)
		os.Exit(0)
	}

	// Initialize zerolog with console output for development
	zerolog.TimeFieldFormat = zerolog.TimeFormatUnix
	log.Logger = zerolog.New(os.Stdout).With().Timestamp().Logger()

	// Load configuration
	cfg, err := config.Load(configPath)
	if err != nil {
		fmt.Printf("Failed to load configuration: %v\n", err)
		os.Exit(1)
	}

	// Override version from build
	if version != "dev" {
		cfg.App.Version = version
	}

	// Initialize logger with configuration
	utils.InitLogger(cfg)

	// Log startup information
	log.Info().
		Str("version", cfg.App.Version).
		Str("environment", cfg.App.Environment).
		Msg("Starting HideMe API Server")

	// Initialize validator
	utils.InitValidator()

	// Create server
	srv, err := server.NewServer(cfg)
	if err != nil {
		log.Fatal().Err(err).Msg("Failed to create server")
	}

	// Set up maintenance tasks
	srv.SetupMaintenanceTasks()

	// Start the server
	if err := srv.Start(); err != nil {
		log.Fatal().Err(err).Msg("Server error")
	}
}
