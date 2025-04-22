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

// Seeder handles database seeding
type Seeder struct {
	db *database.Pool
}

// NewSeeder creates a new seeder
func NewSeeder(db *database.Pool) *Seeder {
	return &Seeder{
		db: db,
	}
}

// SeedDatabase seeds the database with initial data
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

// createSeedsTable creates the seeds table if it doesn't exist
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

// getExecutedSeeds returns a map of executed seeds
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

// runSeed runs a seed function within a transaction
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

// seedDetectionMethods seeds the detection methods
func (s *Seeder) seedDetectionMethods(ctx context.Context, tx *sql.Tx) error {
	// Check if the table is empty
	var count int
	countQuery := `SELECT COUNT(*) FROM detection_methods`
	err := tx.QueryRowContext(ctx, countQuery).Scan(&count)
	if err != nil {
		return err
	}

	// Only seed if the table is empty
	if count == 0 {
		methods := models.DefaultDetectionMethods()

		for _, method := range methods {
			query := `
                INSERT INTO detection_methods (method_name, highlight_color)
                VALUES ($1, $2)
            `
			_, err := tx.ExecContext(ctx, query, method.MethodName, method.HighlightColor)
			if err != nil {
				return err
			}
		}

		log.Info().Int("count", len(methods)).Msg("Seeded detection methods")
	} else {
		log.Debug().Msg("Detection methods already exist, skipping seed")
	}

	return nil
}
