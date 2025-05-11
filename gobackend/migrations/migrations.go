// Package migrations provides a framework for database schema management.
//
// This package implements a migration system that allows for reliable, idempotent
// database schema creation and updates. It tracks executed migrations in a dedicated
// migrations table and ensures all required tables exist before application startup.
//
// The migration system supports:
// - Automatic creation of missing tables
// - Tracking of executed migrations
// - Efficient verification of database schema
// - Idempotent execution of migrations (safe to run multiple times)
package migrations

import (
	"context"
	"database/sql"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
)

// Migration represents a database migration.
// Each migration performs a specific schema change and is tracked
// to ensure it runs exactly once.
type Migration struct {
	// Name is a unique identifier for the migration
	Name string
	// Description is a human-readable explanation of what the migration does
	Description string
	// TableName is the table affected by this migration, used for existence checks
	TableName string
	// RunSQL is the function that executes the migration SQL within a transaction
	RunSQL func(ctx context.Context, tx *sql.Tx) error
}

// Migrator handles database migrations.
// It provides methods to run migrations, check for existing tables,
// and ensure the database schema is up to date.
type Migrator struct {
	db *database.Pool
}

// NewMigrator creates a new migrator.
//
// Parameters:
//   - db: A database connection pool to use for migrations
//
// Returns:
//   - *Migrator: A configured migrator
func NewMigrator(db *database.Pool) *Migrator {
	return &Migrator{
		db: db,
	}
}

// RunMigrations runs all pending database migrations.
// It creates the migrations table if it doesn't exist, verifies all required
// tables exist, and runs any migrations that haven't been executed yet.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//
// Returns:
//   - error: Any error encountered during migration, nil if successful
func (m *Migrator) RunMigrations(ctx context.Context) error {
	log.Info().Msg("Running database migrations")
	startTime := time.Now()

	// Create migrations table if it doesn't exist
	if err := m.createMigrationsTable(ctx); err != nil {
		return fmt.Errorf("failed to create migrations table: %w", err)
	}

	// Verify all tables exist and run missing table migrations
	if err := m.verifyAllTablesExist(ctx); err != nil {
		return fmt.Errorf("failed to verify tables: %w", err)
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
		}
	}

	log.Info().
		Int("migrations_run", migrationsRun).
		Int("migrations_recorded", len(migrations)-len(executedMigrations)).
		Int("total_migrations", len(migrations)).
		Dur("duration", time.Since(startTime)).
		Msg("Database migrations completed")

	if err := m.ensureUserSettingsColumns(ctx); err != nil {
		log.Error().Err(err).Msg("Failed to ensure user_settings columns")
		// Don't return error to avoid breaking existing migrations
	}
	if err := m.ensureUserRoleColumn(ctx); err != nil {
		log.Error().Err(err).Msg("Failed to ensure user role column")
		// Don't return error to avoid breaking existing migrations
	}

	return nil
}

// verifyAllTablesExist checks that all required tables exist, and runs migrations for missing tables.
// This ensures database integrity even if migrations were previously interrupted.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//
// Returns:
//   - error: Any error encountered during verification, nil if successful
func (m *Migrator) verifyAllTablesExist(ctx context.Context) error {
	migrations := GetMigrations()

	for _, migration := range migrations {
		if migration.TableName == "" {
			continue // Skip migrations without a table name
		}

		// Check if the table exists
		exists, err := m.tableExists(ctx, migration.TableName)
		if err != nil {
			return fmt.Errorf("failed to check if table %s exists: %w", migration.TableName, err)
		}

		if !exists {
			log.Warn().
				Str("migration", migration.Name).
				Str("table", migration.TableName).
				Msg("Table doesn't exist but should. Running migration to create it.")

			// Run the migration to create the table
			if err := m.runMigration(ctx, migration); err != nil {
				return fmt.Errorf("failed to create missing table %s: %w", migration.TableName, err)
			}
		}
	}

	return nil
}

// createMigrationsTable creates the migrations table if it doesn't exist.
// This table tracks which migrations have been executed.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//
// Returns:
//   - error: Any error encountered during table creation, nil if successful
func (m *Migrator) createMigrationsTable(ctx context.Context) error {
	query := `
		DROP TABLE IF EXISTS migrations;
		CREATE TABLE migrations (
			name VARCHAR(255) PRIMARY KEY UNIQUE,
			description TEXT,
			executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
	`
	_, err := m.db.ExecContext(ctx, query)
	return err
}

// getExecutedMigrations returns a map of executed migrations.
// The map keys are migration names and values are always true.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//
// Returns:
//   - map[string]bool: A map containing names of executed migrations
//   - error: Any error encountered while retrieving migrations, nil if successful
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

// runMigration runs a migration within a transaction.
// If the migration fails, the transaction is rolled back.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//   - migration: The migration to run
//
// Returns:
//   - error: Any error encountered during migration, nil if successful
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

// recordMigration records a migration as completed without running the SQL.
// This is used when a table already exists but the migration record is missing.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//   - name: The name of the migration to record
//   - description: The description of the migration
//
// Returns:
//   - error: Any error encountered while recording the migration, nil if successful
func (m *Migrator) recordMigration(ctx context.Context, name, description string) error {
	query := `INSERT INTO migrations (name, description) VALUES ($1, $2)`
	_, err := m.db.ExecContext(ctx, query, name, description)
	if err != nil {
		return fmt.Errorf("failed to record migrations: %w", err)
	}
	return nil
}

// tableExists checks if a table exists in the current database schema.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//   - tableName: The name of the table to check
//
// Returns:
//   - bool: True if the table exists, false otherwise
//   - error: Any error encountered during the check, nil if successful
func (m *Migrator) tableExists(ctx context.Context, tableName string) (bool, error) {
	query := `
        SELECT EXISTS(SELECT 1 
        FROM information_schema.tables 
        WHERE table_schema = current_schema()
        AND table_name = $1)
    `
	var exists bool
	err := m.db.QueryRowContext(ctx, query, tableName).Scan(&exists)
	return exists, err
}

// ensureUserSettingsColumns ensures that the user_settings table has all required columns.
// This handles schema evolution without requiring a full migration for minor column additions.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//
// Returns:
//   - error: Any error encountered while ensuring columns exist, nil if successful
func (m *Migrator) ensureUserSettingsColumns(ctx context.Context) error {
	// Check if the detection_threshold column exists
	var columnExists bool
	query := `
		SELECT EXISTS (
			SELECT 1
			FROM information_schema.columns
			WHERE table_name = 'user_settings'
			AND column_name = 'detection_threshold'
		)
	`

	err := m.db.QueryRowContext(ctx, query).Scan(&columnExists)
	if err != nil {
		return fmt.Errorf("failed to check if detection_threshold column exists: %w", err)
	}

	// Add the column if it doesn't exist
	if !columnExists {
		log.Info().Msg("Adding missing detection_threshold column to user_settings table")

		alterQuery := `ALTER TABLE user_settings ADD COLUMN detection_threshold DECIMAL(5, 2) DEFAULT 0.50`
		_, err = m.db.ExecContext(ctx, alterQuery)
		if err != nil {
			return fmt.Errorf("failed to add detection_threshold column: %w", err)
		}

		log.Info().Msg("Successfully added detection_threshold column")
	}

	// Also check for use_banlist_for_detection column
	err = m.db.QueryRowContext(ctx, `
		SELECT EXISTS (
			SELECT 1
			FROM information_schema.columns
			WHERE table_name = 'user_settings'
			AND column_name = 'use_banlist_for_detection'
		)
	`).Scan(&columnExists)

	if err != nil {
		return fmt.Errorf("failed to check if use_banlist_for_detection column exists: %w", err)
	}

	if !columnExists {
		log.Info().Msg("Adding missing use_banlist_for_detection column to user_settings table")

		alterQuery := `ALTER TABLE user_settings ADD COLUMN use_banlist_for_detection BOOLEAN DEFAULT TRUE`
		_, err = m.db.ExecContext(ctx, alterQuery)
		if err != nil {
			return fmt.Errorf("failed to add use_banlist_for_detection column: %w", err)
		}

		log.Info().Msg("Successfully added use_banlist_for_detection column")
	}

	return nil
}

// ensureUserRoleColumn ensures that the users table has a role column.
// This handles schema evolution without requiring a full migration for minor column additions.
//
// Parameters:
//   - ctx: Context for database operations and cancellation
//
// Returns:
//   - error: Any error encountered while ensuring columns exist, nil if successful
func (m *Migrator) ensureUserRoleColumn(ctx context.Context) error {
	// Check if the role column exists
	var columnExists bool
	query := `
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'users'
            AND column_name = 'role'
        )
    `

	err := m.db.QueryRowContext(ctx, query).Scan(&columnExists)
	if err != nil {
		return fmt.Errorf("failed to check if role column exists: %w", err)
	}

	// Add the column if it doesn't exist
	if !columnExists {
		log.Info().Msg("Adding missing role column to users table")

		// TODO check
		alterQuery := `ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user' NOT NULL`
		_, err = m.db.ExecContext(ctx, alterQuery)
		if err != nil {
			return fmt.Errorf("failed to add role column: %w", err)
		}

		log.Info().Msg("Successfully added role column to users table")
	}

	return nil
}

// GetMigrations returns all migrations.
// This function returns a slice of all migrations that the system should apply.
//
// Returns:
//   - []Migration: A slice of all migrations to be applied
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
		createIPBansTable(),              // TODO added this
		createPasswordResetTokensTable(), // Added new migration
	}
}

// createIPBansTable creates the ip_bans table.
// This table stores banned IP addresses and CIDR ranges.
//
// Returns:
//   - Migration: A migration that creates the ip_bans table
func createIPBansTable() Migration {
	return Migration{
		Name:        "create_ip_bans_table",
		Description: "Creates the ip_bans table",
		TableName:   "ip_bans",
		RunSQL: func(ctx context.Context, tx *sql.Tx) error {
			query := `
				CREATE TABLE IF NOT EXISTS ip_bans (
					ban_id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
					ip_address VARCHAR(50) NOT NULL,
					reason TEXT NOT NULL,
					expires_at TIMESTAMP,
					created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
					created_by VARCHAR(100) NOT NULL
				)
			`
			_, err := tx.ExecContext(ctx, query)
			if err != nil {
				return err
			}

			// Create indexes
			indexes := []string{
				`CREATE INDEX IF NOT EXISTS idx_ip_address ON ip_bans(ip_address)`,
				`CREATE INDEX IF NOT EXISTS idx_expires_at ON ip_bans(expires_at)`,
			}

			for _, idx := range indexes {
				_, err = tx.ExecContext(ctx, idx)
				if err != nil {
					return err
				}
			}

			return nil
		},
	}
}
