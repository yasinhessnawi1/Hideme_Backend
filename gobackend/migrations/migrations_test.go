package migrations

import (
	"context"
	"database/sql"
	"github.com/DATA-DOG/go-sqlmock"
	"github.com/stretchr/testify/assert"
	"testing"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
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
	migrator := NewMigrator(pool)

	assert.NotNil(t, migrator)
	assert.Equal(t, pool, migrator.db)
}

// TestCreateMigrationsTable tests the createMigrationsTable function
func TestCreateMigrationsTable(t *testing.T) {
	db, mock, cleanup := createMockDB(t)
	defer cleanup()

	// Expected SQL for creating migrations table
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS migrations").
		WillReturnResult(sqlmock.NewResult(0, 0))

	pool := &database.Pool{DB: db}
	migrator := NewMigrator(pool)

	ctx := context.Background()
	err := migrator.createMigrationsTable(ctx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

// TestGetMigrations tests the GetMigrations function
func TestGetMigrations(t *testing.T) {
	migrations := GetMigrations()

	// We should have at least the basic tables defined
	assert.NotEmpty(t, migrations)

	// Check a few key migrations
	foundUsers := false
	foundDocuments := false

	for _, migration := range migrations {
		if migration.Name == "create_users_table" {
			foundUsers = true
		}
		if migration.Name == "create_documents_table" {
			foundDocuments = true
		}
	}

	assert.True(t, foundUsers, "Should include users table migration")
	assert.True(t, foundDocuments, "Should include documents table migration")
}

// TestMigratorTableExists tests the tableExists function
func TestMigratorTableExists(t *testing.T) {
	db, mock, cleanup := createMockDB(t)
	defer cleanup()

	// Table exists
	mock.ExpectQuery("SELECT COUNT.*FROM information_schema.tables").
		WithArgs("users").
		WillReturnRows(sqlmock.NewRows([]string{"count"}).AddRow(1))

	// Table doesn't exist
	mock.ExpectQuery("SELECT COUNT.*FROM information_schema.tables").
		WithArgs("non_existent_table").
		WillReturnRows(sqlmock.NewRows([]string{"count"}).AddRow(0))

	pool := &database.Pool{DB: db}
	migrator := NewMigrator(pool)

	ctx := context.Background()
	exists, err := migrator.tableExists(ctx, "users")

	assert.NoError(t, err)
	assert.True(t, exists)

	exists, err = migrator.tableExists(ctx, "non_existent_table")

	assert.NoError(t, err)
	assert.False(t, exists)
	assert.NoError(t, mock.ExpectationsWereMet())
}

// Custom transaction executor for testing
type mockTxFn func(*sql.Tx) error

// TestMigrationRunSQL tests a single migration's RunSQL function
func TestMigrationRunSQL(t *testing.T) {

}

// TestRecordMigration tests the recordMigration function
func TestRecordMigration(t *testing.T) {
	db, mock, cleanup := createMockDB(t)
	defer cleanup()

	ctx := context.Background()
	pool := &database.Pool{DB: db}
	migrator := NewMigrator(pool)

	migrationName := "test_migration"
	migrationDesc := "Test migration description"

	mock.ExpectExec("INSERT INTO migrations").
		WithArgs(migrationName, migrationDesc).
		WillReturnResult(sqlmock.NewResult(1, 1))

	err := migrator.recordMigration(ctx, migrationName, migrationDesc)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}
