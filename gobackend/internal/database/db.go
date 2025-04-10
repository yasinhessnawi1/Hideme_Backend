// internal/database/db.go
package database

import (
    "context"
    "database/sql"
    "fmt"
    "os"
    "time"

    _ "github.com/lib/pq" // Import PostgreSQL driver
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
    // Use a longer timeout for database operations
    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()

    // Get connection details from environment variables with fallbacks to config
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

    log.Info().
        Str("host", db_host).
        Str("port", db_port).
        Str("database", db_name).
        Str("user", db_user).
        Msg("Connecting to database")

    // PostgreSQL connection string
    connStr := fmt.Sprintf(
        "host=%s port=%s user=%s password=%s dbname=%s sslmode=disable connect_timeout=15",
        db_host,
        db_port,
        db_user,
        db_password,
        db_name,
    )

    // Connect to the database
    db, err := sql.Open("postgres", connStr)
    if err != nil {
        return nil, fmt.Errorf("failed to connect to database: %w", err)
    }

    // Configure connection pool
    db.SetMaxOpenConns(25)
    db.SetMaxIdleConns(5)
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
