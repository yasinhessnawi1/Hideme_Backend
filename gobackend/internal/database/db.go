// internal/database/db.go
package database

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"time"

	_ "github.com/go-sql-driver/mysql" // Import MySQL driver
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/config"
)

// Pool represents a database connection pool
type Pool struct {
	*sql.DB
}

var (
	// dbPool is the global database connection pool
	dbPool *Pool
)

// Connect creates a new database connection pool
func Connect(cfg *config.AppConfig) (*Pool, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	// load configuration from .env file
	db_host := os.Getenv("DB_HOST")
	db_port := os.Getenv("DB_PORT")
	db_user := os.Getenv("DB_USER")
	db_password := os.Getenv("DB_PASSWORD")
	db_name := os.Getenv("DB_NAME")
	log.Info().
		Str("host", cfg.Database.Host).
		Int("port", cfg.Database.Port).
		Str("database", cfg.Database.Name).
		Str("user", cfg.Database.User).
		Msg("Connecting to database")

	// First, connect without specifying a database
	rootDSN := fmt.Sprintf(
		"%s:%s@tcp(%s:%s)/",
		db_user,
		db_password,
		db_host,
		db_port,
	)

	rootDB, err := sql.Open("mysql", rootDSN)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to root database: %w", err)
	}
	defer rootDB.Close()

	// Try to create the database if it doesn't exist
	_, err = rootDB.ExecContext(ctx, fmt.Sprintf("CREATE DATABASE IF NOT EXISTS %s", db_name))
	if err != nil {
		return nil, fmt.Errorf("failed to create database: %w", err)
	}

	log.Info().Msgf("Ensured database '%s' exists", cfg.Database.Name)

	// Now connect to the actual database
	db, err := sql.Open("mysql", cfg.Database.ConnectionString())
	if err != nil {
		return nil, fmt.Errorf("failed to connect to database: %w", err)
	}

	// Configure connection pool
	db.SetMaxOpenConns(cfg.Database.MaxConns)
	db.SetMaxIdleConns(cfg.Database.MinConns)
	db.SetConnMaxLifetime(1 * time.Hour)
	db.SetConnMaxIdleTime(30 * time.Minute)

	// Verify connection
	if err := db.PingContext(ctx); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}

	log.Info().Msg("Successfully connected to database")

	// Create and store the global database pool
	dbPool = &Pool{DB: db}
	return dbPool, nil
}

// Get returns the global database connection pool
func Get() *Pool {
	if dbPool == nil {
		log.Fatal().Msg("database connection pool not initialized")
	}
	return dbPool
}

// Close closes the database connection pool
func (p *Pool) Close() {
	if p != nil && p.DB != nil {
		log.Info().Msg("Closing database connection pool")
		p.DB.Close()
	}
}

// Transaction executes a function within a transaction
func (p *Pool) Transaction(ctx context.Context, fn func(tx *sql.Tx) error) error {
	// Start a transaction
	tx, err := p.BeginTx(ctx, nil)
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

// HealthCheck performs a health check on the database connection
func (p *Pool) HealthCheck(ctx context.Context) error {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	if err := p.PingContext(ctx); err != nil {
		return fmt.Errorf("database health check failed: %w", err)
	}

	// Run a simple query to verify database functionality
	var result int
	if err := p.QueryRowContext(ctx, "SELECT 1").Scan(&result); err != nil {
		return fmt.Errorf("database query test failed: %w", err)
	}

	if result != 1 {
		return fmt.Errorf("database returned unexpected result: %d", result)
	}

	return nil
}
