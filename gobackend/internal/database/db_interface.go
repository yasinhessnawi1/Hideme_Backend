// Package database provides database access and management functions for the HideMe API.
// It implements a connection pool, transaction management, and common database operations.
package database

import (
	"context"
	"database/sql"
	"time"
)

// SQLDatabase defines the interface for database operations.
// This interface abstracts the underlying database implementation,
// allowing for easier testing with mock implementations.
//
// It includes all the essential methods from sql.DB that are used
// by the application, making it easier to create test doubles.
type SQLDatabase interface {
	// Begin starts a transaction.
	Begin() (*sql.Tx, error)

	// BeginTx starts a transaction with the provided context and options.
	BeginTx(ctx context.Context, opts *sql.TxOptions) (*sql.Tx, error)

	// Close closes the database, releasing any open resources.
	Close() error

	// Exec executes a query without returning any rows.
	Exec(query string, args ...interface{}) (sql.Result, error)

	// ExecContext executes a query with the provided context without returning any rows.
	ExecContext(ctx context.Context, query string, args ...interface{}) (sql.Result, error)

	// Ping verifies a connection to the database is still alive.
	Ping() error

	// PingContext verifies a connection to the database is still alive using the provided context.
	PingContext(ctx context.Context) error

	// Prepare creates a prepared statement for later queries or executions.
	Prepare(query string) (*sql.Stmt, error)

	// PrepareContext creates a prepared statement for later queries or executions using the provided context.
	PrepareContext(ctx context.Context, query string) (*sql.Stmt, error)

	// Query executes a query that returns rows.
	Query(query string, args ...interface{}) (*sql.Rows, error)

	// QueryContext executes a query with the provided context that returns rows.
	QueryContext(ctx context.Context, query string, args ...interface{}) (*sql.Rows, error)

	// QueryRow executes a query that is expected to return at most one row.
	QueryRow(query string, args ...interface{}) *sql.Row

	// QueryRowContext executes a query with the provided context that is expected to return at most one row.
	QueryRowContext(ctx context.Context, query string, args ...interface{}) *sql.Row

	// SetConnMaxIdleTime sets the maximum amount of time a connection may be idle.
	SetConnMaxIdleTime(d time.Duration)

	// SetConnMaxLifetime sets the maximum amount of time a connection may be reused.
	SetConnMaxLifetime(d time.Duration)

	// SetMaxIdleConns sets the maximum number of connections in the idle connection pool.
	SetMaxIdleConns(n int)

	// SetMaxOpenConns sets the maximum number of open connections to the database.
	SetMaxOpenConns(n int)
}

// Ensure sql.DB implements SQLDatabase.
// This is a compile-time check to verify that sql.DB implements all the methods
// defined in the SQLDatabase interface.
var _ SQLDatabase = (*sql.DB)(nil)
