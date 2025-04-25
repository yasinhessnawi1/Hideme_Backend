package migrations_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/stretchr/testify/assert"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/migrations"
)

// createMockDB creates a mock database for testing
func createMockDB(t *testing.T) (*sql.DB, sqlmock.Sqlmock, func()) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("Failed to create mock database: %v", err)
	}

	cleanup := func() {
		db.Close()
	}

	return db, mock, cleanup
}

// TestNewMigrator tests the NewMigrator function
func TestNewMigrator(t *testing.T) {
	db, _, cleanup := createMockDB(t)
	defer cleanup()

	pool := &database.Pool{DB: db}
	migrator := migrations.NewMigrator(pool)

	assert.NotNil(t, migrator)
}

// TestGetMigrations tests the GetMigrations function
func TestGetMigrations(t *testing.T) {
	migrations := migrations.GetMigrations()

	// We should have at least the basic tables defined
	assert.NotEmpty(t, migrations)

	// Check a few key migrations
	foundUsers := false
	foundDocuments := false
	foundSessions := false
	foundAPIKeys := false

	for _, migration := range migrations {
		switch migration.Name {
		case "create_users_table":
			foundUsers = true
			assert.Equal(t, "users", migration.TableName)
		case "create_documents_table":
			foundDocuments = true
			assert.Equal(t, "documents", migration.TableName)
		case "create_sessions_table":
			foundSessions = true
			assert.Equal(t, "sessions", migration.TableName)
		case "create_api_keys_table":
			foundAPIKeys = true
			assert.Equal(t, "api_keys", migration.TableName)
		}
	}

	assert.True(t, foundUsers, "Should include users table migration")
	assert.True(t, foundDocuments, "Should include documents table migration")
	assert.True(t, foundSessions, "Should include sessions table migration")
	assert.True(t, foundAPIKeys, "Should include API keys table migration")
}

// TestRunMigrations tests the main RunMigrations function with various scenarios
func TestRunMigrations(t *testing.T) {
	tests := []struct {
		name           string
		setup          func(sqlmock.Sqlmock)
		wantErr        bool
		expectedErrMsg string // Optional: check specific error message
	}{
		{
			name: "Error - Create migrations table fails",
			setup: func(mock sqlmock.Sqlmock) {
				// Expect DROP TABLE and CREATE TABLE, but return an error
				mock.ExpectExec("DROP TABLE IF EXISTS migrations").
					WillReturnError(errors.New("failed to drop migrations table"))
			},
			wantErr:        true,
			expectedErrMsg: "failed to create migrations table",
		},
		{
			name: "Error - Table exists check fails during verify step",
			setup: func(mock sqlmock.Sqlmock) {
				// Create migrations table succeeds
				mock.ExpectExec("DROP TABLE IF EXISTS migrations").
					WillReturnResult(sqlmock.NewResult(0, 0))

				// First tableExists check fails - Update to match actual SQL query
				mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM information_schema.tables").
					WithArgs("users").
					WillReturnError(errors.New("failed to check table existence"))
			},
			wantErr:        true,
			expectedErrMsg: "failed to verify tables",
		},
		{
			name: "Error - Get executed migrations fails",
			setup: func(mock sqlmock.Sqlmock) {
				// Create migrations table succeeds
				mock.ExpectExec("DROP TABLE IF EXISTS migrations").
					WillReturnResult(sqlmock.NewResult(0, 0))

				// Set up expectations for verifyAllTablesExist
				// Each migration's table already exists
				migrations := migrations.GetMigrations()
				for _, migration := range migrations {
					if migration.TableName != "" {
						mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM information_schema.tables").
							WithArgs(migration.TableName).
							WillReturnRows(sqlmock.NewRows([]string{"exists"}).AddRow(1)) // Return 1 instead of true
					}
				}

				// Get executed migrations fails
				mock.ExpectQuery("SELECT name FROM migrations").
					WillReturnError(errors.New("failed to get executed migrations"))
			},
			wantErr:        true,
			expectedErrMsg: "failed to get executed migrations",
		},
		{
			name: "Error - Migration execution fails",
			setup: func(mock sqlmock.Sqlmock) {
				// Create migrations table succeeds
				mock.ExpectExec("DROP TABLE IF EXISTS migrations").
					WillReturnResult(sqlmock.NewResult(0, 0))

				// Set up failed table existence check for first table to trigger migration
				mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM information_schema.tables").
					WithArgs("users").
					WillReturnRows(sqlmock.NewRows([]string{"exists"}).AddRow(0)) // Return 0 instead of false

				// Begin transaction
				mock.ExpectBegin()

				// Migration execution fails
				mock.ExpectExec("CREATE TABLE").
					WillReturnError(errors.New("migration execution failed"))

				// Transaction rollback
				mock.ExpectRollback()
			},
			wantErr:        true,
			expectedErrMsg: "migration execution failed",
		},
		{
			name: "Success - All migrations already executed",
			setup: func(mock sqlmock.Sqlmock) {
				// Create migrations table
				mock.ExpectExec("DROP TABLE IF EXISTS migrations").
					WillReturnResult(sqlmock.NewResult(0, 0))

				// All tables already exist
				migrations := migrations.GetMigrations()
				for _, migration := range migrations {
					if migration.TableName != "" {
						mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM information_schema.tables").
							WithArgs(migration.TableName).
							WillReturnRows(sqlmock.NewRows([]string{"exists"}).AddRow(1)) // Return 1 instead of true
					}
				}

				// Get all migration names for the executed migrations
				migrationRows := sqlmock.NewRows([]string{"name"})
				for _, m := range migrations {
					migrationRows.AddRow(m.Name)
				}

				// Return that all migrations have been executed
				mock.ExpectQuery("SELECT name FROM migrations").
					WillReturnRows(migrationRows)

				// Check detection_threshold column exists
				mock.ExpectQuery("SELECT EXISTS").
					WillReturnRows(sqlmock.NewRows([]string{"exists"}).AddRow(1)) // Return 1 instead of true

				// Check use_banlist_for_detection column exists
				mock.ExpectQuery("SELECT EXISTS").
					WillReturnRows(sqlmock.NewRows([]string{"exists"}).AddRow(1)) // Return 1 instead of true
			},
			wantErr: false,
		},
		{
			name: "Success - Add missing columns to user_settings",
			setup: func(mock sqlmock.Sqlmock) {
				// Create migrations table
				mock.ExpectExec("DROP TABLE IF EXISTS migrations").
					WillReturnResult(sqlmock.NewResult(0, 0))

				// All tables already exist
				migrations := migrations.GetMigrations()
				for _, migration := range migrations {
					if migration.TableName != "" {
						mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM information_schema.tables").
							WithArgs(migration.TableName).
							WillReturnRows(sqlmock.NewRows([]string{"exists"}).AddRow(1)) // Return 1 instead of true
					}
				}

				// Get all migration names for the executed migrations
				migrationRows := sqlmock.NewRows([]string{"name"})
				for _, m := range migrations {
					migrationRows.AddRow(m.Name)
				}

				// Return that all migrations have been executed
				mock.ExpectQuery("SELECT name FROM migrations").
					WillReturnRows(migrationRows)

				// Check detection_threshold column doesn't exist
				mock.ExpectQuery("SELECT EXISTS").
					WillReturnRows(sqlmock.NewRows([]string{"exists"}).AddRow(0)) // Return 0 instead of false

				// Add the missing column
				mock.ExpectExec("ALTER TABLE user_settings ADD COLUMN detection_threshold").
					WillReturnResult(sqlmock.NewResult(0, 0))

				// Check use_banlist_for_detection column doesn't exist
				mock.ExpectQuery("SELECT EXISTS").
					WillReturnRows(sqlmock.NewRows([]string{"exists"}).AddRow(0)) // Return 0 instead of false

				// Add the missing column
				mock.ExpectExec("ALTER TABLE user_settings ADD COLUMN use_banlist_for_detection").
					WillReturnResult(sqlmock.NewResult(0, 0))
			},
			wantErr: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			db, mock, cleanup := createMockDB(t)
			defer cleanup()

			tt.setup(mock)

			pool := &database.Pool{DB: db}
			migrator := migrations.NewMigrator(pool)

			ctx := context.Background()
			err := migrator.RunMigrations(ctx)

			if tt.wantErr {
				assert.Error(t, err)
				if tt.expectedErrMsg != "" {
					assert.Contains(t, err.Error(), tt.expectedErrMsg)
				}
			} else {
				assert.NoError(t, err)
			}

			if err := mock.ExpectationsWereMet(); err != nil {
				t.Errorf("There were unfulfilled expectations: %s", err)
			}
		})
	}
}

// TestRunSQL tests individual migration's RunSQL functions
func TestRunSQL(t *testing.T) {
	// Test RunSQL for a specific migration
	migrationsList := migrations.GetMigrations()

	if len(migrationsList) == 0 {
		t.Skip("No migrations to test")
	}

	// Test the first migration's RunSQL function
	firstMigration := migrationsList[0]

	t.Run("RunSQL - "+firstMigration.Name, func(t *testing.T) {
		db, mock, cleanup := createMockDB(t)
		defer cleanup()

		ctx := context.Background()

		// Begin transaction for the test
		mock.ExpectBegin()
		tx, err := db.Begin()
		assert.NoError(t, err)

		// Expect the SQL from the migration
		mock.ExpectExec("CREATE TABLE IF NOT EXISTS").
			WillReturnResult(sqlmock.NewResult(0, 0))

		// Run the migration's SQL
		err = firstMigration.RunSQL(ctx, tx)

		assert.NoError(t, err)
		assert.NoError(t, mock.ExpectationsWereMet())
	})
}

// TestMigrationProperties tests that all migrations have the required properties
func TestMigrationProperties(t *testing.T) {
	migrations := migrations.GetMigrations()

	for _, migration := range migrations {
		t.Run(migration.Name, func(t *testing.T) {
			assert.NotEmpty(t, migration.Name, "Migration should have a name")
			assert.NotEmpty(t, migration.Description, "Migration should have a description")
			assert.NotEmpty(t, migration.TableName, "Migration should have a table name")
			assert.NotNil(t, migration.RunSQL, "Migration should have a RunSQL function")
		})
	}
}

// TestTransactionBehavior tests transaction behavior in various scenarios
func TestTransactionBehavior(t *testing.T) {
	t.Run("Transaction rollback on failure", func(t *testing.T) {
		db, mock, cleanup := createMockDB(t)
		defer cleanup()

		// Set up expectations
		mock.ExpectBegin()
		mock.ExpectExec("CREATE TABLE IF NOT EXISTS test_table").
			WillReturnError(errors.New("migration failed"))
		mock.ExpectRollback()

		pool := &database.Pool{DB: db}

		// Migration that fails
		failingMigration := migrations.Migration{
			Name:        "failing_migration",
			Description: "Migration that fails",
			RunSQL: func(ctx context.Context, tx *sql.Tx) error {
				_, err := tx.ExecContext(ctx, "CREATE TABLE IF NOT EXISTS test_table")
				return err
			},
		}

		ctx := context.Background()

		// Use the Pool's Transaction method to test transaction behavior
		err := pool.Transaction(ctx, func(tx *sql.Tx) error {
			// Run the migration
			if err := failingMigration.RunSQL(ctx, tx); err != nil {
				return err
			}

			// Record the migration - this line won't be reached due to the error above
			_, err := tx.ExecContext(ctx, "INSERT INTO migrations (name, description) VALUES ($1, $2)", failingMigration.Name, failingMigration.Description)
			return err
		})

		assert.Error(t, err)
		assert.NoError(t, mock.ExpectationsWereMet())
	})
}

// BenchmarkMigrations benchmarks the migration process
func BenchmarkMigrations(b *testing.B) {
	db, mock, cleanup := createMockDB(nil)
	defer cleanup()

	pool := &database.Pool{DB: db}
	migrator := migrations.NewMigrator(pool)

	ctx := context.Background()

	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		// Set up expectations for each iteration
		mock.ExpectExec("CREATE TABLE IF NOT EXISTS migrations").
			WillReturnResult(sqlmock.NewResult(0, 0))
		rows := sqlmock.NewRows([]string{"name"})
		mock.ExpectQuery("SELECT name FROM migrations").
			WillReturnRows(rows)

		_ = migrator.RunMigrations(ctx)
	}
}
