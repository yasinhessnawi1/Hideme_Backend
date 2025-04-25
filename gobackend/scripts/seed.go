// Package scripts provides utility scripts for database and system management.
//
// This package implements database seeding functionality to populate initial data
// required for the application to function properly. The seeding system works
// similarly to migrations, tracking executed seeds to ensure they only run once,
// making the process idempotent and safe to run on both new and existing databases.
package scripts

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

// Seeder handles database seeding.
// It provides methods to run seeds that populate the database
// with initial required data.
type Seeder struct {
	db *database.Pool
}

// NewSeeder creates a new seeder.
//
// Parameters:
//   - db: A database connection pool to use for seeding
//
// Returns:
//   - *Seeder: A configured seeder
func NewSeeder(db *database.Pool) *Seeder {
	return &Seeder{
		db: db,
	}
}

// SeedDatabase seeds the database with initial data.
// It creates the seeds tracking table if it doesn't exist, then runs
// all seed functions that haven't been executed yet.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//
// Returns:
//   - error: Any error encountered during seeding, nil if successful
func (s *Seeder) SeedDatabase(ctx context.Context) error {
	log.Info().Msg("Seeding database")
	startTime := time.Now()

	// Create seeds table if it doesn't exist
	if err := s.createSeedsTable(ctx); err != nil {
		return fmt.Errorf("failed to create seeds table: %w", err)
	}

	// Get executed seeds
	executedSeeds, err := s.getExecutedSeeds(ctx)
	if err != nil {
		return fmt.Errorf("failed to get executed seeds: %w", err)
	}

	// Run seeds that haven't been executed yet
	seeds := []struct {
		Name     string
		SeedFunc func(ctx context.Context, tx *sql.Tx) error
	}{
		{"detection_methods", s.seedDetectionMethods},
		// Add more seeds here if needed
	}

	for _, seed := range seeds {
		if !executedSeeds[seed.Name] {
			log.Info().Str("seed", seed.Name).Msg("Running seed")
			if err := s.runSeed(ctx, seed.Name, seed.SeedFunc); err != nil {
				return err
			}
		} else {
			log.Debug().Str("seed", seed.Name).Msg("Seed already executed")
		}
	}

	log.Info().
		Dur("duration", time.Since(startTime)).
		Msg("Database seeding completed")

	return nil
}

// createSeedsTable creates the seeds table if it doesn't exist.
// This table tracks which seed operations have been executed.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//
// Returns:
//   - error: Any error encountered during table creation, nil if successful
func (s *Seeder) createSeedsTable(ctx context.Context) error {
	query := `
		DROP TABLE IF EXISTS seeds;
		CREATE TABLE  seeds (
			name VARCHAR(255) PRIMARY KEY,
			executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
	`
	_, err := s.db.ExecContext(ctx, query)
	return err
}

// getExecutedSeeds returns a map of executed seeds.
// The map keys are seed names and values are always true.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//
// Returns:
//   - map[string]bool: A map containing names of executed seeds
//   - error: Any error encountered while retrieving seeds, nil if successful
func (s *Seeder) getExecutedSeeds(ctx context.Context) (map[string]bool, error) {
	query := `SELECT name FROM seeds`
	rows, err := s.db.QueryContext(ctx, query)
	if err != nil {
		return nil, err
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	seeds := make(map[string]bool)
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, err
		}
		seeds[name] = true
	}

	return seeds, rows.Err()
}

// runSeed runs a seed function within a transaction.
// If the seed operation fails, the transaction is rolled back.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//   - name: The name of the seed operation
//   - seedFunc: The function that performs the seeding
//
// Returns:
//   - error: Any error encountered during seeding, nil if successful
func (s *Seeder) runSeed(ctx context.Context, name string, seedFunc func(ctx context.Context, tx *sql.Tx) error) error {
	return s.db.Transaction(ctx, func(tx *sql.Tx) error {
		// Run the seed
		if err := seedFunc(ctx, tx); err != nil {
			return fmt.Errorf("seed %s failed: %w", name, err)
		}

		// Record the seed
		query := `INSERT INTO seeds (name) VALUES ($1)` // PostgreSQL syntax
		_, err := tx.ExecContext(ctx, query, name)
		if err != nil {
			return fmt.Errorf("failed to record seed: %w", err)
		}

		return nil
	})
}

// seedDetectionMethods seeds the detection_methods table with default values.
// This ensures all standard detection methods are available in the system.
// It checks for existing methods to avoid duplicates.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//   - tx: The SQL transaction to use for the operation
//
// Returns:
//   - error: Any error encountered during seeding, nil if successful
func (s *Seeder) seedDetectionMethods(ctx context.Context, tx *sql.Tx) error {
	methods := models.DefaultDetectionMethods()

	// First, verify if detection methods already exist
	var methodCount int
	countQuery := `SELECT COUNT(*) FROM detection_methods`
	err := tx.QueryRowContext(ctx, countQuery).Scan(&methodCount)
	if err != nil {
		return fmt.Errorf("failed to count detection methods: %w", err)
	}

	// Get existing method names to avoid duplicates
	existingMethods := make(map[string]bool)
	if methodCount > 0 {
		query := `SELECT method_name FROM detection_methods`
		rows, err := tx.QueryContext(ctx, query)
		if err != nil {
			return fmt.Errorf("failed to query existing methods: %w", err)
		}
		defer rows.Close()

		for rows.Next() {
			var methodName string
			if err := rows.Scan(&methodName); err != nil {
				return err
			}
			existingMethods[methodName] = true
		}

		if err := rows.Err(); err != nil {
			return err
		}
	}

	// Insert missing methods
	insertedCount := 0
	for _, method := range methods {
		if !existingMethods[method.MethodName] {
			query := `
                INSERT INTO detection_methods (method_name, highlight_color)
                VALUES ($1, $2)
            `
			_, err := tx.ExecContext(ctx, query, method.MethodName, method.HighlightColor)
			if err != nil {
				return fmt.Errorf("failed to insert detection method %s: %w", method.MethodName, err)
			}
			insertedCount++
		}
	}

	log.Info().
		Int("existing_methods", methodCount).
		Int("inserted_methods", insertedCount).
		Msg("Detection methods seeding completed")

	return nil
}
