package migrations

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
)

// Migration represents a database migrations
type Migration struct {
	Name        string
	Description string
	TableName   string // Added to store the table name for existence check
	RunSQL      func(ctx context.Context, tx *sql.Tx) error
}

// Migrator handles database migrations
type Migrator struct {
	db *database.Pool
}

// NewMigrator creates a new migrator
func NewMigrator(db *database.Pool) *Migrator {
	return &Migrator{
		db: db,
	}
}

// RunMigrations runs all migrations
func (m *Migrator) RunMigrations(ctx context.Context) error {
	log.Info().Msg("Running database migrations")
	startTime := time.Now()

	// Create migrations table if it doesn't exist
	if err := m.createMigrationsTable(ctx); err != nil {
		return fmt.Errorf("failed to create migrations table: %w", err)
	}

	// Get executed migrations
	executedMigrations, err := m.getExecutedMigrations(ctx)
	if err != nil {
		return fmt.Errorf("failed to get executed migrations: %w", err)
	}

	// Run migrations that haven't been executed yet
	migrations := GetMigrations()
	migrationsRun := 0

	for _, migration := range migrations {
		if _, ok := executedMigrations[migration.Name]; !ok {
			// Check if the table already exists before running the migrations
			exists, err := m.tableExists(ctx, migration.TableName)
			if err != nil {
				return fmt.Errorf("failed to check if table %s exists: %w", migration.TableName, err)
			}

			if exists {
				log.Info().
					Str("migrations", migration.Name).
					Str("table", migration.TableName).
					Msg("Table already exists, recording migrations as completed")

				// Record the migrations as completed without running the SQL
				if err := m.recordMigration(ctx, migration.Name, migration.Description); err != nil {
					return fmt.Errorf("failed to record existing migrations: %w", err)
				}
			} else {
				log.Info().
					Str("migrations", migration.Name).
					Str("table", migration.TableName).
					Msg("Running migrations")

				if err := m.runMigration(ctx, migration); err != nil {
					return err
				}
				migrationsRun++
			}
		} else {
			log.Debug().
				Str("migrations", migration.Name).
				Msg("Migration already executed")
		}
	}

	log.Info().
		Int("migrations_run", migrationsRun).
		Int("migrations_recorded", len(migrations)-len(executedMigrations)).
		Int("total_migrations", len(migrations)).
		Dur("duration", time.Since(startTime)).
		Msg("Database migrations completed")

	return nil
}

// createMigrationsTable creates the migrations table if it doesn't exist
func (m *Migrator) createMigrationsTable(ctx context.Context) error {
	query := `
		CREATE TABLE IF NOT EXISTS migrations (
			name VARCHAR(255) PRIMARY KEY,
			description TEXT,
			executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
	`
	_, err := m.db.ExecContext(ctx, query)
	return err
}

// getExecutedMigrations returns a map of executed migrations
func (m *Migrator) getExecutedMigrations(ctx context.Context) (map[string]bool, error) {
	query := `SELECT name FROM migrations`
	rows, err := m.db.QueryContext(ctx, query)
	if err != nil {
		return nil, err
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	migrations := make(map[string]bool)
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, err
		}
		migrations[name] = true
	}

	return migrations, rows.Err()
}

// runMigration runs a migrations within a transaction
func (m *Migrator) runMigration(ctx context.Context, migration Migration) error {
	return m.db.Transaction(ctx, func(tx *sql.Tx) error {
		// Run the migrations
		if err := migration.RunSQL(ctx, tx); err != nil {
			return fmt.Errorf("migrations %s failed: %w", migration.Name, err)
		}

		// Record the migrations
		query := `INSERT INTO migrations (name, description) VALUES ($1, $2)`
		_, err := tx.ExecContext(ctx, query, migration.Name, migration.Description)
		if err != nil {
			return fmt.Errorf("failed to record migrations: %w", err)
		}

		return nil
	})
}

// recordMigration records a migrations as completed without running the SQL
func (m *Migrator) recordMigration(ctx context.Context, name, description string) error {
	query := `INSERT INTO migrations (name, description) VALUES ($1, $2)`
	_, err := m.db.ExecContext(ctx, query, name, description)
	if err != nil {
		return fmt.Errorf("failed to record migrations: %w", err)
	}
	return nil
}

// tableExists checks if a table exists in the database
func (m *Migrator) tableExists(ctx context.Context, tableName string) (bool, error) {
	query := `
		SELECT COUNT(*)
		FROM information_schema.tables
		WHERE table_schema = current_schema()
		AND table_name = $1
	`
	var count int
	err := m.db.QueryRowContext(ctx, query, tableName).Scan(&count)
	return count > 0, err
}

// GetMigrations returns all migrations
func GetMigrations() []Migration {
	return []Migration{
		createUsersTable(),
		createUserSettingsTable(),
		createDocumentsTable(),
		createDetectionMethodsTable(),
		createDetectedEntitiesTable(),
		createModelEntitiesTable(),
		createSearchPatternsTable(),
		createBanListTable(),
		createBanListWordsTable(),
		createSessionsTable(),
		createAPIKeysTable(),
	}
}
