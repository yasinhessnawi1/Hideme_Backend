package scripts

import (
	"context"
	"database/sql"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/stretchr/testify/assert"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
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

// createMockDBAndTx creates a mock database and transaction for testing
func createMockDBAndTx(t *testing.T) (*sql.DB, *sql.Tx, sqlmock.Sqlmock, func()) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("Failed to create mock database: %v", err)
	}

	mock.ExpectBegin()
	tx, err := db.Begin()
	if err != nil {
		t.Fatalf("Failed to create transaction: %v", err)
	}

	cleanup := func() {
		tx.Rollback()
		db.Close()
	}

	return db, tx, mock, cleanup
}

func TestNewSeeder(t *testing.T) {
	db, _, cleanup := createMockDB(t)
	defer cleanup()

	pool := &database.Pool{DB: db}
	seeder := NewSeeder(pool)

	assert.NotNil(t, seeder)
	assert.Equal(t, pool, seeder.db)
}

func TestCreateSeedsTable(t *testing.T) {
	db, mock, cleanup := createMockDB(t)
	defer cleanup()

	// drop the table to ensure creating new table in the sql query
	mock.ExpectExec("DROP TABLE IF EXISTS seeds").
		WillReturnResult(sqlmock.NewResult(0, 0))

	pool := &database.Pool{DB: db}
	seeder := NewSeeder(pool)

	ctx := context.Background()
	err := seeder.createSeedsTable(ctx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestGetExecutedSeeds(t *testing.T) {
	db, mock, cleanup := createMockDB(t)
	defer cleanup()

	ctx := context.Background()

	// Mock the SELECT query
	mock.ExpectQuery("SELECT name FROM seeds").
		WillReturnRows(sqlmock.NewRows([]string{"name"}).
			AddRow("detection_methods"))

	pool := &database.Pool{DB: db}
	seeder := NewSeeder(pool)

	seeds, err := seeder.getExecutedSeeds(ctx)

	assert.NoError(t, err)
	assert.NotNil(t, seeds)
	assert.True(t, seeds["detection_methods"])
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestRunSeed(t *testing.T) {
	db, mock, cleanup := createMockDB(t)
	defer cleanup()

	ctx := context.Background()
	seedName := "test_seed"

	// Mock BeginTx, execution, and commit
	mock.ExpectBegin()
	mock.ExpectExec("INSERT INTO seeds").
		WithArgs(seedName).
		WillReturnResult(sqlmock.NewResult(1, 1))
	mock.ExpectCommit()

	pool := &database.Pool{DB: db}
	seeder := NewSeeder(pool)

	// Create a test seed function
	seedFn := func(ctx context.Context, tx *sql.Tx) error {
		return nil
	}

	// Run the seed function
	err := seeder.runSeed(ctx, seedName, seedFn)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSeedDetectionMethods(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	ctx := context.Background()

	// Mock the count query to return 0 (empty table)
	mock.ExpectQuery("SELECT COUNT.*FROM detection_methods").
		WillReturnRows(sqlmock.NewRows([]string{"count"}).AddRow(0))

	// Get the default methods to know how many insertions to expect
	methods := models.DefaultDetectionMethods()

	// Expect an insert for each method
	for _, method := range methods {
		mock.ExpectExec("INSERT INTO detection_methods").
			WithArgs(method.MethodName, method.HighlightColor).
			WillReturnResult(sqlmock.NewResult(1, 1))
	}

	// Create a new seeder
	db, _, _ := createMockDB(t)
	pool := &database.Pool{DB: db}
	seeder := NewSeeder(pool)

	// Test the seed function
	err := seeder.seedDetectionMethods(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSeedDetectionMethodsWithExistingData(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	ctx := context.Background()

	// Mock the count query to return a value > 0 (table has data)
	mock.ExpectQuery("SELECT COUNT.*FROM detection_methods").
		WillReturnRows(sqlmock.NewRows([]string{"count"}).AddRow(5))

	// No insertions should be attempted

	// Create a new seeder
	db, _, _ := createMockDB(t)
	pool := &database.Pool{DB: db}
	seeder := NewSeeder(pool)

	// Test the seed function
	err := seeder.seedDetectionMethods(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSeedDatabaseWithExistingSeeds(t *testing.T) {
	db, mock, cleanup := createMockDB(t)
	defer cleanup()

	ctx := context.Background()

	// drop the table to ensure creating new table in the sql query
	mock.ExpectExec("DROP TABLE IF EXISTS seeds").
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Mock getExecutedSeeds - all seeds already exist
	mock.ExpectQuery("SELECT name FROM seeds").
		WillReturnRows(sqlmock.NewRows([]string{"name"}).
			AddRow("detection_methods"))

	// No further transactions should be attempted

	pool := &database.Pool{DB: db}
	seeder := NewSeeder(pool)

	// Run the seed database function
	err := seeder.SeedDatabase(ctx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}
