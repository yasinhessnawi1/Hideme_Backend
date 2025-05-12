package database

import (
	"context"
	"database/sql"
	"errors"
	"os"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/stretchr/testify/assert"
)

// TestNilConnectionHandling tests handling of nil connections
func TestNilConnectionHandling(t *testing.T) {
	t.Run("Close with nil DB pointer", func(t *testing.T) {
		// Create a pool with a nil DB pointer
		pool := &Pool{DB: nil}

		// This should not panic
		pool.Close()
	})

	t.Run("Close with nil pool", func(t *testing.T) {
		// Create a nil pool
		var pool *Pool

		// This should not panic
		pool.Close()
	})
}

// TestGet tests the Get function
func TestGet(t *testing.T) {
	// Backup and restore the global dbPool
	originalDBPool := dbPool
	defer func() {
		dbPool = originalDBPool
	}()

	t.Run("Get with initialized pool", func(t *testing.T) {
		// Create a mock DB
		mockDB, _, err := sqlmock.New()
		if err != nil {
			t.Fatalf("Error creating mock database: %v", err)
		}
		defer mockDB.Close()

		// Set the global pool
		mockPool := &Pool{DB: mockDB}
		dbPool = mockPool

		// Call Get
		result := Get()
		assert.Equal(t, mockPool, result)
	})

}

// TestClose tests the Close function
func TestClose(t *testing.T) {
	t.Run("Close with valid pool", func(t *testing.T) {
		// Create a mock DB
		mockDB, mock, err := sqlmock.New()
		if err != nil {
			t.Fatalf("Error creating mock database: %v", err)
		}

		// Create pool
		pool := &Pool{DB: mockDB}

		// Set up expectations
		mock.ExpectClose()

		// Call Close
		pool.Close()

		// Verify expectations were met
		err = mock.ExpectationsWereMet()
		assert.NoError(t, err)
	})

	t.Run("Close with nil pool", func(t *testing.T) {
		// Create pool with nil DB
		pool := &Pool{DB: nil}

		// Call Close - should not panic
		pool.Close()
	})

	t.Run("Close with nil", func(t *testing.T) {
		// Create nil pool
		var pool *Pool = nil

		// Call Close - should not panic
		pool.Close()
	})
}

// TestTransaction tests the Transaction function
func TestTransaction(t *testing.T) {
	t.Run("Successful transaction", func(t *testing.T) {
		// Create a mock DB
		mockDB, mock, err := sqlmock.New()
		if err != nil {
			t.Fatalf("Error creating mock database: %v", err)
		}
		defer mockDB.Close()

		// Create pool
		pool := &Pool{DB: mockDB}

		// Set up expectations
		mock.ExpectBegin()
		mock.ExpectCommit()

		// Create a context
		ctx := context.Background()

		// Call Transaction with a function that succeeds
		err = pool.Transaction(ctx, func(tx *sql.Tx) error {
			return nil
		})

		// Verify no error and expectations were met
		assert.NoError(t, err)
		err = mock.ExpectationsWereMet()
		assert.NoError(t, err)
	})

	t.Run("Begin transaction failure", func(t *testing.T) {
		// Create a mock DB
		mockDB, mock, err := sqlmock.New()
		if err != nil {
			t.Fatalf("Error creating mock database: %v", err)
		}
		defer mockDB.Close()

		// Create pool
		pool := &Pool{DB: mockDB}

		// Set up expectations - BeginTx returns error
		mock.ExpectBegin().WillReturnError(errors.New("begin error"))

		// Create a context
		ctx := context.Background()

		// Call Transaction
		err = pool.Transaction(ctx, func(tx *sql.Tx) error {
			return nil
		})

		// Verify error and expectations were met
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "failed to begin transaction")
		err = mock.ExpectationsWereMet()
		assert.NoError(t, err)
	})

	t.Run("Function returns error", func(t *testing.T) {
		// Create a mock DB
		mockDB, mock, err := sqlmock.New()
		if err != nil {
			t.Fatalf("Error creating mock database: %v", err)
		}
		defer mockDB.Close()

		// Create pool
		pool := &Pool{DB: mockDB}

		// Set up expectations
		mock.ExpectBegin()
		mock.ExpectRollback()

		// Create a context
		ctx := context.Background()

		// Call Transaction with a function that returns an error
		funcErr := errors.New("function error")
		err = pool.Transaction(ctx, func(tx *sql.Tx) error {
			return funcErr
		})

		// Verify we get the function error and expectations were met
		assert.Equal(t, funcErr, err)
		err = mock.ExpectationsWereMet()
		assert.NoError(t, err)
	})

	t.Run("Rollback failure after function error", func(t *testing.T) {
		// Create a mock DB
		mockDB, mock, err := sqlmock.New()
		if err != nil {
			t.Fatalf("Error creating mock database: %v", err)
		}
		defer mockDB.Close()

		// Create pool
		pool := &Pool{DB: mockDB}

		// Set up expectations
		mock.ExpectBegin()
		mock.ExpectRollback().WillReturnError(errors.New("rollback error"))

		// Create a context
		ctx := context.Background()

		// Call Transaction with a function that returns an error
		funcErr := errors.New("function error")
		err = pool.Transaction(ctx, func(tx *sql.Tx) error {
			return funcErr
		})

		// Verify we get the rollback error
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "failed to rollback transaction")
		err = mock.ExpectationsWereMet()
		assert.NoError(t, err)
	})

	t.Run("Commit failure", func(t *testing.T) {
		// Create a mock DB
		mockDB, mock, err := sqlmock.New()
		if err != nil {
			t.Fatalf("Error creating mock database: %v", err)
		}
		defer mockDB.Close()

		// Create pool
		pool := &Pool{DB: mockDB}

		// Set up expectations
		mock.ExpectBegin()
		mock.ExpectCommit().WillReturnError(errors.New("commit error"))

		// Create a context
		ctx := context.Background()

		// Call Transaction with a function that succeeds
		err = pool.Transaction(ctx, func(tx *sql.Tx) error {
			return nil
		})

		// Verify commit error and expectations were met
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "failed to commit transaction")
		err = mock.ExpectationsWereMet()
		assert.NoError(t, err)
	})

	t.Run("Panic in function", func(t *testing.T) {
		// Create a mock DB
		mockDB, mock, err := sqlmock.New()
		if err != nil {
			t.Fatalf("Error creating mock database: %v", err)
		}
		defer mockDB.Close()

		// Create pool
		pool := &Pool{DB: mockDB}

		// Set up expectations
		mock.ExpectBegin()
		mock.ExpectRollback()

		// Create a context
		ctx := context.Background()

		// Call Transaction with a function that panics
		defer func() {
			r := recover()
			assert.NotNil(t, r)
			assert.Equal(t, "panic test", r)

			// Verify expectations were met
			err = mock.ExpectationsWereMet()
			assert.NoError(t, err)
		}()

		_ = pool.Transaction(ctx, func(tx *sql.Tx) error {
			panic("panic test")
		})
	})

	t.Run("Panic in function with rollback error", func(t *testing.T) {
		// Create a mock DB
		mockDB, mock, err := sqlmock.New()
		if err != nil {
			t.Fatalf("Error creating mock database: %v", err)
		}
		defer mockDB.Close()

		// Create pool
		pool := &Pool{DB: mockDB}

		// Set up expectations
		mock.ExpectBegin()
		mock.ExpectRollback().WillReturnError(errors.New("rollback error"))

		// Create a context
		ctx := context.Background()

		// Call Transaction with a function that panics
		defer func() {
			r := recover()
			assert.NotNil(t, r)
			assert.Equal(t, "panic test", r)

			// Verify expectations were met
			err = mock.ExpectationsWereMet()
			assert.NoError(t, err)
		}()

		_ = pool.Transaction(ctx, func(tx *sql.Tx) error {
			panic("panic test")
		})
	})
}

// TestHealthCheck tests the HealthCheck function
func TestHealthCheck(t *testing.T) {
	t.Run("Successful health check", func(t *testing.T) {
		// Create a mock DB
		mockDB, mock, err := sqlmock.New()
		if err != nil {
			t.Fatalf("Error creating mock database: %v", err)
		}
		defer mockDB.Close()

		// Create pool
		pool := &Pool{DB: mockDB}

		// Set up expectations
		mock.ExpectPing()
		mock.ExpectQuery("SELECT 1").WillReturnRows(sqlmock.NewRows([]string{"1"}).AddRow(1))

		// Create a context
		ctx := context.Background()

		// Call HealthCheck
		err = pool.HealthCheck(ctx)

		// Verify no error and expectations were met
		assert.NoError(t, err)
		err = mock.ExpectationsWereMet()
		assert.NoError(t, err)
	})

	t.Run("Query failure", func(t *testing.T) {
		// Create a mock DB
		mockDB, mock, err := sqlmock.New()
		if err != nil {
			t.Fatalf("Error creating mock database: %v", err)
		}
		defer mockDB.Close()

		// Create pool
		pool := &Pool{DB: mockDB}

		// Set up expectations
		mock.ExpectPing()
		mock.ExpectQuery("SELECT 1").WillReturnError(errors.New("query error"))

		// Create a context
		ctx := context.Background()

		// Call HealthCheck
		err = pool.HealthCheck(ctx)

		// Verify error and expectations were met
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "database query test failed")
		err = mock.ExpectationsWereMet()
		assert.NoError(t, err)
	})

	t.Run("Unexpected result", func(t *testing.T) {
		// Create a mock DB
		mockDB, mock, err := sqlmock.New()
		if err != nil {
			t.Fatalf("Error creating mock database: %v", err)
		}
		defer mockDB.Close()

		// Create pool
		pool := &Pool{DB: mockDB}

		// Set up expectations
		mock.ExpectPing()
		mock.ExpectQuery("SELECT 1").WillReturnRows(sqlmock.NewRows([]string{"1"}).AddRow(2))

		// Create a context
		ctx := context.Background()

		// Call HealthCheck
		err = pool.HealthCheck(ctx)

		// Verify error and expectations were met
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "database returned unexpected result")
		err = mock.ExpectationsWereMet()
		assert.NoError(t, err)
	})
}

func TestConnect(t *testing.T) {

}

// TestEnvVariables tests handling of environment variables
func TestEnvVariables(t *testing.T) {

}

// TestMain is the entry point for testing
func TestMain(m *testing.M) {
	// Run the tests
	result := m.Run()

	// Exit with the test result
	os.Exit(result)
}
