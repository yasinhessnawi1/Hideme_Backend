// Package database provides database access and management functions for the HideMe API.
// It implements a connection pool, transaction management, and common database operations.
//
// The package uses the standard database/sql package with the PostgreSQL driver,
// and provides a higher-level abstraction for common database operations.
// It includes health checks, connection management, and proper error handling.
package database

import (
	"context"
	"database/sql"
	"fmt"
	"os"

	_ "github.com/lib/pq" // Import PostgreSQL driver
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// Pool represents a database connection pool.
// It embeds sql.DB to provide direct access to its methods while allowing
// for extension with additional functionality.
type Pool struct {
	*sql.DB
}

var (
	// dbPool is the global database connection pool.
	// It's initialized by Connect() and accessed via Get().
	dbPool *Pool
)

// Connect creates a new database connection pool using the provided configuration.
// It establishes a connection to the database, configures connection pool parameters,
// and verifies the connection before returning.
//
// Parameters:
//   - cfg: The application configuration containing database settings
//
// Returns:
//   - A properly initialized database connection pool
//   - An error if connection fails
func Connect(cfg *config.AppConfig) (*Pool, error) {
	// Use a longer timeout for database operations during initial connection
	ctx, cancel := context.WithTimeout(context.Background(), constants.DBConnectionTimeout)
	defer cancel()

	// Get connection details from environment variables with fallbacks to config
	// This allows for runtime configuration overrides
	db_host := os.Getenv("DB_HOST")
	if db_host == "" {
		db_host = cfg.Database.Host
	}

	db_port := os.Getenv("DB_PORT")
	if db_port == "" {
		db_port = fmt.Sprintf("%d", cfg.Database.Port)
	}

	db_user := os.Getenv("DB_USER")
	if db_user == "" {
		db_user = cfg.Database.User
	}

	db_password := os.Getenv("DB_PASSWORD")
	if db_password == "" {
		db_password = cfg.Database.Password
	}

	db_name := os.Getenv("DB_NAME")
	if db_name == "" {
		db_name = cfg.Database.Name
	}

	// Determine SSL parameters based on environment
	var sslParams string
	if cfg.App.Environment == "dev" || cfg.App.Environment == "development" {
		sslParams = constants.PostgresSSLDisable
	} else if cfg.App.Environment == "prod" {
		sslParams = constants.PostgresSSLParams
	} else {
		sslParams = constants.PostgresSSLParams
	}

	// Log connection attempt (without sensitive information)
	log.Info().
		Str("host", db_host).
		Str("port", db_port).
		Str("database", db_name).
		Str("user", db_user).
		Msg("Connecting to database")

	// PostgreSQL connection string with safety parameters
	connStr := fmt.Sprintf(
		"host=%s port=%s user=%s password=%s dbname=%s %s",
		db_host,
		db_port,
		db_user,
		db_password,
		db_name,
		sslParams,
	)

	// Open a connection to the database
	// Note: This doesn't actually establish a connection yet, it just validates parameters
	db, err := sql.Open("postgres", connStr)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to database: %w", err)
	}

	// Configure connection pool parameters for optimal performance
	db.SetMaxOpenConns(cfg.Database.MaxConns)          // Maximum number of open connections
	db.SetMaxIdleConns(cfg.Database.MinConns)          // Minimum number of idle connections
	db.SetConnMaxLifetime(constants.DBConnMaxLifetime) // Maximum lifetime of a connection
	db.SetConnMaxIdleTime(constants.DBConnMaxIdleTime) // Maximum idle time of a connection

	// Verify connection with a ping
	// This ensures we can actually establish a connection before returning
	if err := db.PingContext(ctx); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	log.Info().Msg("Successfully connected to database")

	// Create and store the global database pool
	dbPool = &Pool{DB: db}
	return dbPool, nil
}

// Get returns the global database connection pool.
// This provides global access to the database connection after it has been initialized.
//
// Returns:
//   - The global database connection pool
//
// Panics:
//   - If the database connection pool hasn't been initialized
func Get() *Pool {
	if dbPool == nil {
		log.Fatal().Msg("database connection pool not initialized")
	}
	return dbPool
}

// Close closes the database connection pool.
// This should be called when the application shuts down to release resources.
func (p *Pool) Close() {
	if p != nil && p.DB != nil {
		log.Info().Msg("Closing database connection pool")
		p.DB.Close()
	}
}

// Transaction executes a function within a database transaction.
// It handles starting the transaction, committing on success, rolling back on error,
// and properly handling panics to ensure the transaction is always cleaned up.
//
// Parameters:
//   - ctx: The context for the transaction
//   - fn: The function to execute within the transaction
//
// Returns:
//   - An error if the transaction fails or the function returns an error
func (p *Pool) Transaction(ctx context.Context, fn func(tx *sql.Tx) error) error {
	// Start a transaction
	tx, err := p.DB.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("failed to begin transaction: %w", err)
	}

	// Handle panics to ensure proper rollback
	defer func() {
		if r := recover(); r != nil {
			// Rollback the transaction in case of panic
			if rbErr := tx.Rollback(); rbErr != nil {
				log.Error().Err(rbErr).Msg("Failed to rollback transaction after panic")
			}
			// Re-throw the panic
			panic(r)
		}
	}()

	// Execute the function within the transaction
	if err := fn(tx); err != nil {
		// Rollback the transaction on error
		if rbErr := tx.Rollback(); rbErr != nil {
			return fmt.Errorf("failed to rollback transaction: %w", rbErr)
		}
		return err
	}

	// Commit the transaction
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	return nil
}

// HealthCheck performs a health check on the database connection.
// It verifies that the database is reachable and operational by
// pinging it and executing a simple query.
//
// Parameters:
//   - ctx: The context for the health check
//
// Returns:
//   - An error if the health check fails, nil if the database is healthy
func (p *Pool) HealthCheck(ctx context.Context) error {
	// Use a timeout to prevent the health check from hanging
	ctx, cancel := context.WithTimeout(ctx, constants.DBHealthCheckTimeout)
	defer cancel()

	// Ping the database to verify connection
	if err := p.DB.PingContext(ctx); err != nil {
		return fmt.Errorf("database health check failed: %w", err)
	}

	// Run a simple query to verify database functionality
	var result int
	if err := p.DB.QueryRowContext(ctx, "SELECT 1").Scan(&result); err != nil {
		return fmt.Errorf("database query test failed: %w", err)
	}

	// Verify that the result is what we expect
	if result != 1 {
		return fmt.Errorf("database returned unexpected result: %d", result)
	}

	return nil
}
