package repository_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
)

// setupSessionRepositoryTest creates a new test database connection and mock
func setupSessionRepositoryTest(t *testing.T) (*repository.MysqlSessionRepository, sqlmock.Sqlmock, func()) {
	// Create a new SQL mock database
	db, mock, err := sqlmock.New()
	require.NoError(t, err)

	// Create a database pool with the mock database
	dbPool := &database.Pool{DB: db}

	// Create a new repository with the mocked database
	repo := repository.NewSessionRepository(dbPool).(*repository.MysqlSessionRepository)

	// Return the repository, mock and a cleanup function
	return repo, mock, func() {
		db.Close()
	}
}

func TestSessionRepository_Create(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	session := &models.Session{
		ID:        "session123",
		UserID:    100,
		JWTID:     "jwt456",
		ExpiresAt: now.Add(24 * time.Hour),
		CreatedAt: now,
	}

	// Expected query with placeholders for the arguments
	mock.ExpectExec("INSERT INTO sessions").
		WithArgs(session.ID, session.UserID, session.JWTID, session.ExpiresAt, session.CreatedAt).
		WillReturnResult(sqlmock.NewResult(1, 1))

	// Execute the method being tested
	err := repo.Create(context.Background(), session)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_Create_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	session := &models.Session{
		ID:        "session123",
		UserID:    100,
		JWTID:     "jwt456",
		ExpiresAt: now.Add(24 * time.Hour),
		CreatedAt: now,
	}

	// Mock database error
	mock.ExpectExec("INSERT INTO sessions").
		WithArgs(session.ID, session.UserID, session.JWTID, session.ExpiresAt, session.CreatedAt).
		WillReturnError(errors.New("database error"))

	// Execute the method being tested
	err := repo.Create(context.Background(), session)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to create session")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_GetByID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := "session123"
	now := time.Now()
	session := &models.Session{
		ID:        id,
		UserID:    100,
		JWTID:     "jwt456",
		ExpiresAt: now.Add(24 * time.Hour),
		CreatedAt: now,
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"session_id", "user_id", "jwt_id", "expires_at", "created_at"}).
		AddRow(session.ID, session.UserID, session.JWTID, session.ExpiresAt, session.CreatedAt)

	// Expected query with placeholder for the ID
	mock.ExpectQuery("SELECT session_id, user_id, jwt_id, expires_at, created_at FROM sessions WHERE session_id = ?").
		WithArgs(id).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, session.ID, result.ID)
	assert.Equal(t, session.UserID, result.UserID)
	assert.Equal(t, session.JWTID, result.JWTID)
	assert.WithinDuration(t, session.ExpiresAt, result.ExpiresAt, time.Second)
	assert.WithinDuration(t, session.CreatedAt, result.CreatedAt, time.Second)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_GetByID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := "nonexistent-session"

	// Mock database response - empty result
	mock.ExpectQuery("SELECT session_id, user_id, jwt_id, expires_at, created_at FROM sessions WHERE session_id = ?").
		WithArgs(id).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_GetByJWTID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	jwtID := "jwt456"
	now := time.Now()
	session := &models.Session{
		ID:        "session123",
		UserID:    100,
		JWTID:     jwtID,
		ExpiresAt: now.Add(24 * time.Hour),
		CreatedAt: now,
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"session_id", "user_id", "jwt_id", "expires_at", "created_at"}).
		AddRow(session.ID, session.UserID, session.JWTID, session.ExpiresAt, session.CreatedAt)

	// Expected query with placeholder for the JWT ID
	mock.ExpectQuery("SELECT session_id, user_id, jwt_id, expires_at, created_at FROM sessions WHERE jwt_id = ?").
		WithArgs(jwtID).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByJWTID(context.Background(), jwtID)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, session.ID, result.ID)
	assert.Equal(t, session.UserID, result.UserID)
	assert.Equal(t, session.JWTID, result.JWTID)
	assert.WithinDuration(t, session.ExpiresAt, result.ExpiresAt, time.Second)
	assert.WithinDuration(t, session.CreatedAt, result.CreatedAt, time.Second)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_GetByJWTID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	jwtID := "nonexistent-jwt"

	// Mock database response - empty result
	mock.ExpectQuery("SELECT session_id, user_id, jwt_id, expires_at, created_at FROM sessions WHERE jwt_id = ?").
		WithArgs(jwtID).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByJWTID(context.Background(), jwtID)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_GetActiveByUserID(t *testing.T) {

}

func TestSessionRepository_Delete(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := "session123"

	// Expected query with placeholder for the ID
	mock.ExpectExec("DELETE FROM sessions WHERE session_id = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_Delete_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := "nonexistent-session"

	// Expected query with placeholder for the ID, but no rows affected
	mock.ExpectExec("DELETE FROM sessions WHERE session_id = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_DeleteByJWTID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	jwtID := "jwt456"

	// Expected query with placeholder for the JWT ID
	mock.ExpectExec("DELETE FROM sessions WHERE jwt_id = ?").
		WithArgs(jwtID).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.DeleteByJWTID(context.Background(), jwtID)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_DeleteByJWTID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	jwtID := "nonexistent-jwt"

	// Expected query with placeholder for the JWT ID, but no rows affected
	mock.ExpectExec("DELETE FROM sessions WHERE jwt_id = ?").
		WithArgs(jwtID).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.DeleteByJWTID(context.Background(), jwtID)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_DeleteByUserID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Expected query with placeholder for the user ID
	mock.ExpectExec("DELETE FROM sessions WHERE user_id = ?").
		WithArgs(userID).
		WillReturnResult(sqlmock.NewResult(0, 3)) // 3 sessions deleted

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_DeleteExpired(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Expected query with placeholder for current time
	mock.ExpectExec("DELETE FROM sessions WHERE expires_at < ?").
		WithArgs(sqlmock.AnyArg()).
		WillReturnResult(sqlmock.NewResult(0, 5)) // 5 expired sessions deleted

	// Execute the method being tested
	count, err := repo.DeleteExpired(context.Background())

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(5), count)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_IsValidSession(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	jwtID := "jwt456"

	// Set up query result - session exists and is not expired
	rows := sqlmock.NewRows([]string{"exists"}).AddRow(1)

	// Expected query with placeholders for JWT ID and current time
	mock.ExpectQuery("SELECT EXISTS").
		WithArgs(jwtID, sqlmock.AnyArg()).
		WillReturnRows(rows)

	// Execute the method being tested
	isValid, err := repo.IsValidSession(context.Background(), jwtID)

	// Assert the results
	assert.NoError(t, err)
	assert.True(t, isValid)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestSessionRepository_IsValidSession_Invalid(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupSessionRepositoryTest(t)
	defer cleanup()

	// Set up test data
	jwtID := "invalid-jwt"

	// Set up query result - session doesn't exist or is expired
	rows := sqlmock.NewRows([]string{"exists"}).AddRow(0)

	// Expected query with placeholders for JWT ID and current time
	mock.ExpectQuery("SELECT EXISTS").
		WithArgs(jwtID, sqlmock.AnyArg()).
		WillReturnRows(rows)

	// Execute the method being tested
	isValid, err := repo.IsValidSession(context.Background(), jwtID)

	// Assert the results
	assert.NoError(t, err)
	assert.False(t, isValid)
	assert.NoError(t, mock.ExpectationsWereMet())
}
