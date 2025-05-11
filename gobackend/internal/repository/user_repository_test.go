package repository_test

import (
	"context"
	"database/sql"
	"errors"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/lib/pq"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
)

// setupUserRepositoryTest creates a new test database connection and mock
func setupUserRepositoryTest(t *testing.T) (*repository.PostgresUserRepository, sqlmock.Sqlmock, func()) {
	// Create a new SQL mock database
	db, mock, err := sqlmock.New()
	require.NoError(t, err)

	// Create a database pool with the mock database
	dbPool := &database.Pool{DB: db}

	// Create a new repository with the mocked database
	repo := repository.NewUserRepository(dbPool).(*repository.PostgresUserRepository)

	// Return the repository, mock and a cleanup function
	return repo, mock, func() {
		db.Close()
	}
}

func TestUserRepository_Create(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		Role:         "user", // Add the role field
		CreatedAt:    time.Time{},
		UpdatedAt:    time.Time{},
	}

	// Setup for PostgreSQL RETURNING clause
	rows := sqlmock.NewRows([]string{"user_id"}).AddRow(1)

	// Expected query with placeholders for the arguments
	mock.ExpectQuery("INSERT INTO users").
		WithArgs(
			user.Username,
			user.Email,
			user.PasswordHash,
			user.Salt,
			user.Role,        // Include role argument
			sqlmock.AnyArg(), // CreatedAt can be any time
			sqlmock.AnyArg(), // UpdatedAt can be any time
		).
		WillReturnRows(rows)

	// Execute the method being tested
	err := repo.Create(context.Background(), user)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(1), user.ID) // ID should be set from RETURNING clause
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Create_DatabaseError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		Role:         "user", // Add the role field
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	// Mock database error
	mock.ExpectQuery("INSERT INTO users").
		WithArgs(
			user.Username,
			user.Email,
			user.PasswordHash,
			user.Salt,
			user.Role,        // Include role argument
			sqlmock.AnyArg(), // CreatedAt
			sqlmock.AnyArg(), // UpdatedAt
		).
		WillReturnError(errors.New("database connection error"))

	// Execute the method being tested
	err := repo.Create(context.Background(), user)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to create user")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Create_DuplicateUsername(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	user := &models.User{
		Username:     "duplicate",
		Email:        "test@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		Role:         "user", // Add the role field
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	// Mock unique constraint violation
	pqErr := &pq.Error{
		Code:       "23505", // unique_violation
		Constraint: "idx_username",
		Message:    "duplicate key value violates unique constraint \"idx_username\"",
	}

	mock.ExpectQuery("INSERT INTO users").
		WithArgs(
			user.Username,
			user.Email,
			user.PasswordHash,
			user.Salt,
			user.Role,        // Include role argument
			sqlmock.AnyArg(), // CreatedAt
			sqlmock.AnyArg(), // UpdatedAt
		).
		WillReturnError(pqErr)

	// Execute the method being tested
	err := repo.Create(context.Background(), user)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "duplicate")
	assert.Contains(t, err.Error(), "username")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Create_PQError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		Role:         "user", // Add the role field
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	// Mock other PostgreSQL error
	pqErr := &pq.Error{
		Code:    "23503", // foreign_key_violation
		Message: "Foreign key violation",
	}

	mock.ExpectQuery("INSERT INTO users").
		WithArgs(
			user.Username,
			user.Email,
			user.PasswordHash,
			user.Salt,
			user.Role,        // Include role argument
			sqlmock.AnyArg(), // CreatedAt
			sqlmock.AnyArg(), // UpdatedAt
		).
		WillReturnError(pqErr)

	// Execute the method being tested
	err := repo.Create(context.Background(), user)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to create user")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_GetByID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)
	now := time.Now()
	expectedUser := &models.User{
		ID:           id,
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		Role:         "user", // Add the role field
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	// Set up query result - include role field
	rows := sqlmock.NewRows([]string{"user_id", "username", "email", "password_hash", "salt", "role", "created_at", "updated_at"}).
		AddRow(expectedUser.ID, expectedUser.Username, expectedUser.Email, expectedUser.PasswordHash, expectedUser.Salt, expectedUser.Role, expectedUser.CreatedAt, expectedUser.UpdatedAt)

	// Expected query with placeholder for the ID - include role in SELECT
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, role, created_at, updated_at FROM users WHERE user_id = \\$1").
		WithArgs(id).
		WillReturnRows(rows)

	// Execute the method being tested
	user, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.NotNil(t, user)
	assert.Equal(t, expectedUser.ID, user.ID)
	assert.Equal(t, expectedUser.Username, user.Username)
	assert.Equal(t, expectedUser.Email, user.Email)
	assert.Equal(t, expectedUser.PasswordHash, user.PasswordHash)
	assert.Equal(t, expectedUser.Salt, user.Salt)
	assert.Equal(t, expectedUser.Role, user.Role)
	assert.Equal(t, expectedUser.CreatedAt, user.CreatedAt)
	assert.Equal(t, expectedUser.UpdatedAt, user.UpdatedAt)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_GetByID_DatabaseError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Mock database error - update the regex to include role
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, role, created_at, updated_at FROM users WHERE user_id = \\$1").
		WithArgs(id).
		WillReturnError(errors.New("database connection error"))

	// Execute the method being tested
	user, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, user)
	assert.Contains(t, err.Error(), "failed to get user by ID")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_GetByID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Mock not found error - update the regex to include role
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, role, created_at, updated_at FROM users WHERE user_id = \\$1").
		WithArgs(id).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	user, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, user)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_GetByUsername(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	username := "testuser"
	now := time.Now()
	expectedUser := &models.User{
		ID:           1,
		Username:     username,
		Email:        "test@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		Role:         "user", // Add the role field
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	// Set up query result - include role field
	rows := sqlmock.NewRows([]string{"user_id", "username", "email", "password_hash", "salt", "role", "created_at", "updated_at"}).
		AddRow(expectedUser.ID, expectedUser.Username, expectedUser.Email, expectedUser.PasswordHash, expectedUser.Salt, expectedUser.Role, expectedUser.CreatedAt, expectedUser.UpdatedAt)

	// Expected query with placeholder for the username - include role in SELECT
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, role, created_at, updated_at FROM users WHERE LOWER\\(username\\) = LOWER\\(\\$1\\)").
		WithArgs(username).
		WillReturnRows(rows)

	// Execute the method being tested
	user, err := repo.GetByUsername(context.Background(), username)

	// Assert the results
	assert.NoError(t, err)
	assert.NotNil(t, user)
	assert.Equal(t, expectedUser.ID, user.ID)
	assert.Equal(t, expectedUser.Username, user.Username)
	assert.Equal(t, expectedUser.Email, user.Email)
	assert.Equal(t, expectedUser.PasswordHash, user.PasswordHash)
	assert.Equal(t, expectedUser.Salt, user.Salt)
	assert.Equal(t, expectedUser.Role, user.Role)
	assert.Equal(t, expectedUser.CreatedAt, user.CreatedAt)
	assert.Equal(t, expectedUser.UpdatedAt, user.UpdatedAt)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_GetByUsername_DatabaseError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	username := "testuser"

	// Mock a database error
	dbErr := errors.New("database connection error")
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, created_at, updated_at FROM users WHERE LOWER\\(username\\) = LOWER\\(\\$1\\)").
		WithArgs(username).
		WillReturnError(dbErr)

	// Execute the method being tested
	result, err := repo.GetByUsername(context.Background(), username)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.Contains(t, err.Error(), "failed to get user by username")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_GetByUsername_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	username := "nonexistent"

	// Mock database response - empty result
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, created_at, updated_at FROM users WHERE LOWER\\(username\\) = LOWER\\(\\$1\\)").
		WithArgs(username).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByUsername(context.Background(), username)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_GetByEmail(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	email := "test@example.com"
	now := time.Now()
	user := &models.User{
		ID:           1,
		Username:     "testuser",
		Email:        email,
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"user_id", "username", "email", "password_hash", "salt", "created_at", "updated_at"}).
		AddRow(user.ID, user.Username, user.Email, user.PasswordHash, user.Salt, user.CreatedAt, user.UpdatedAt)

	// Expected query with placeholder for the email (case-insensitive comparison for PostgreSQL)
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, created_at, updated_at FROM users WHERE LOWER\\(email\\) = LOWER\\(\\$1\\)").
		WithArgs(email).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByEmail(context.Background(), email)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, user.ID, result.ID)
	assert.Equal(t, user.Username, result.Username)
	assert.Equal(t, user.Email, result.Email)
	assert.Equal(t, user.PasswordHash, result.PasswordHash)
	assert.Equal(t, user.Salt, result.Salt)
	assert.WithinDuration(t, user.CreatedAt, result.CreatedAt, time.Second)
	assert.WithinDuration(t, user.UpdatedAt, result.UpdatedAt, time.Second)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_GetByEmail_DatabaseError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	email := "test@example.com"

	// Mock a database error
	dbErr := errors.New("database connection error")
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, created_at, updated_at FROM users WHERE LOWER\\(email\\) = LOWER\\(\\$1\\)").
		WithArgs(email).
		WillReturnError(dbErr)

	// Execute the method being tested
	result, err := repo.GetByEmail(context.Background(), email)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.Contains(t, err.Error(), "failed to get user by email")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_GetByEmail_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	email := "nonexistent@example.com"

	// Mock database response - empty result
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, created_at, updated_at FROM users WHERE LOWER\\(email\\) = LOWER\\(\\$1\\)").
		WithArgs(email).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByEmail(context.Background(), email)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Update(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	user := &models.User{
		ID:           1,
		Username:     "updateduser",
		Email:        "updated@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		CreatedAt:    now.Add(-time.Hour),
		UpdatedAt:    now,
	}

	// Expected query with placeholders for the arguments
	mock.ExpectExec("UPDATE users SET username = \\$1, email = \\$2, updated_at = \\$3 WHERE user_id = \\$4").
		WithArgs(user.Username, user.Email, sqlmock.AnyArg(), user.ID).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.Update(context.Background(), user)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Update_DatabaseError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	user := &models.User{
		ID:           1,
		Username:     "updateduser",
		Email:        "updated@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		CreatedAt:    now.Add(-time.Hour),
		UpdatedAt:    now,
	}

	// Mock a database error
	dbErr := errors.New("database connection error")
	mock.ExpectExec("UPDATE users SET username = \\$1, email = \\$2, updated_at = \\$3 WHERE user_id = \\$4").
		WithArgs(user.Username, user.Email, sqlmock.AnyArg(), user.ID).
		WillReturnError(dbErr)

	// Execute the method being tested
	err := repo.Update(context.Background(), user)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to update user")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Update_RowsAffectedError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	user := &models.User{
		ID:           1,
		Username:     "updateduser",
		Email:        "updated@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		CreatedAt:    now.Add(-time.Hour),
		UpdatedAt:    now,
	}

	// Create a result that will error on RowsAffected
	result := sqlmock.NewErrorResult(errors.New("rows affected error"))

	mock.ExpectExec("UPDATE users SET username = \\$1, email = \\$2, updated_at = \\$3 WHERE user_id = \\$4").
		WithArgs(user.Username, user.Email, sqlmock.AnyArg(), user.ID).
		WillReturnResult(result)

	// Execute the method being tested
	err := repo.Update(context.Background(), user)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get rows affected")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Update_DuplicateUsername(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	user := &models.User{
		ID:           1,
		Username:     "duplicateuser",
		Email:        "updated@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		CreatedAt:    now.Add(-time.Hour),
		UpdatedAt:    now,
	}

	// Mock a PostgreSQL duplicate key error with specific constraint name for username
	duplicateErr := errors.New(`pq: duplicate key value violates unique constraint "idx_username"`)
	mock.ExpectExec("UPDATE users SET username = \\$1, email = \\$2, updated_at = \\$3 WHERE user_id = \\$4").
		WithArgs(user.Username, user.Email, sqlmock.AnyArg(), user.ID).
		WillReturnError(duplicateErr)

	// Execute the method being tested
	err := repo.Update(context.Background(), user)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "duplicate")
	assert.Contains(t, err.Error(), "username")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Update_DuplicateEmail(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	user := &models.User{
		ID:           1,
		Username:     "updateduser",
		Email:        "duplicate@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		CreatedAt:    now.Add(-time.Hour),
		UpdatedAt:    now,
	}

	// Mock a PostgreSQL duplicate key error with specific constraint name for email
	duplicateErr := errors.New(`pq: duplicate key value violates unique constraint "idx_email"`)
	mock.ExpectExec("UPDATE users SET username = \\$1, email = \\$2, updated_at = \\$3 WHERE user_id = \\$4").
		WithArgs(user.Username, user.Email, sqlmock.AnyArg(), user.ID).
		WillReturnError(duplicateErr)

	// Execute the method being tested
	err := repo.Update(context.Background(), user)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "duplicate")
	assert.Contains(t, err.Error(), "email")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Update_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	user := &models.User{
		ID:           999,
		Username:     "updateduser",
		Email:        "updated@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		CreatedAt:    now.Add(-time.Hour),
		UpdatedAt:    now,
	}

	// Expected query with placeholders, but no rows affected
	mock.ExpectExec("UPDATE users SET username = \\$1, email = \\$2, updated_at = \\$3 WHERE user_id = \\$4").
		WithArgs(user.Username, user.Email, sqlmock.AnyArg(), user.ID).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Update(context.Background(), user)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Delete(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Set up transaction expectations
	mock.ExpectBegin()
	mock.ExpectExec("DELETE FROM users WHERE user_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Delete_BeginError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Mock a transaction begin error
	beginErr := errors.New("begin transaction error")
	mock.ExpectBegin().WillReturnError(beginErr)

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to begin transaction")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Delete_ExecError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Set up transaction expectations with exec error
	mock.ExpectBegin()
	execErr := errors.New("exec error")
	mock.ExpectExec("DELETE FROM users WHERE user_id = \\$1").
		WithArgs(id).
		WillReturnError(execErr)
	mock.ExpectRollback() // Should rollback on error

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to delete user")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Delete_CommitError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Set up transaction expectations with commit error
	mock.ExpectBegin()
	mock.ExpectExec("DELETE FROM users WHERE user_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 1))
	commitErr := errors.New("commit error")
	mock.ExpectCommit().WillReturnError(commitErr)

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to commit transaction")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Delete_RollbackError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Set up transaction expectations with exec and rollback errors
	mock.ExpectBegin()
	execErr := errors.New("exec error")
	mock.ExpectExec("DELETE FROM users WHERE user_id = \\$1").
		WithArgs(id).
		WillReturnError(execErr)
	rollbackErr := errors.New("rollback error")
	mock.ExpectRollback().WillReturnError(rollbackErr)

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	// The implementation seems to return the rollback error rather than the original exec error
	assert.Contains(t, err.Error(), "rollback")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Delete_RowsAffectedError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)

	// Set up transaction expectations with rows affected error
	mock.ExpectBegin()
	result := sqlmock.NewErrorResult(errors.New("rows affected error"))
	mock.ExpectExec("DELETE FROM users WHERE user_id = \\$1").
		WithArgs(id).
		WillReturnResult(result)
	mock.ExpectRollback() // Should rollback on error

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get rows affected")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Delete_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Set up transaction expectations
	mock.ExpectBegin()
	mock.ExpectExec("DELETE FROM users WHERE user_id = \\$1").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not found")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ChangePassword(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)
	passwordHash := "new_hashed_password"
	salt := "new_salt_value"

	// Expected query with placeholders for the arguments
	mock.ExpectExec("UPDATE users SET password_hash = \\$1, salt = \\$2, updated_at = \\$3 WHERE user_id = \\$4").
		WithArgs(passwordHash, salt, sqlmock.AnyArg(), id).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.ChangePassword(context.Background(), id, passwordHash, salt)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ChangePassword_DatabaseError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)
	passwordHash := "new_hashed_password"
	salt := "new_salt_value"

	// Mock a database error
	dbErr := errors.New("database connection error")
	mock.ExpectExec("UPDATE users SET password_hash = \\$1, salt = \\$2, updated_at = \\$3 WHERE user_id = \\$4").
		WithArgs(passwordHash, salt, sqlmock.AnyArg(), id).
		WillReturnError(dbErr)

	// Execute the method being tested
	err := repo.ChangePassword(context.Background(), id, passwordHash, salt)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to update password")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ChangePassword_RowsAffectedError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)
	passwordHash := "new_hashed_password"
	salt := "new_salt_value"

	// Create a result that will error on RowsAffected
	result := sqlmock.NewErrorResult(errors.New("rows affected error"))

	mock.ExpectExec("UPDATE users SET password_hash = \\$1, salt = \\$2, updated_at = \\$3 WHERE user_id = \\$4").
		WithArgs(passwordHash, salt, sqlmock.AnyArg(), id).
		WillReturnResult(result)

	// Execute the method being tested
	err := repo.ChangePassword(context.Background(), id, passwordHash, salt)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to get rows affected")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ChangePassword_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)
	passwordHash := "new_hashed_password"
	salt := "new_salt_value"

	// Expected query with placeholders, but no rows affected
	mock.ExpectExec("UPDATE users SET password_hash = \\$1, salt = \\$2, updated_at = \\$3 WHERE user_id = \\$4").
		WithArgs(passwordHash, salt, sqlmock.AnyArg(), id).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.ChangePassword(context.Background(), id, passwordHash, salt)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "not found")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ExistsByUsername(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	username := "existinguser"

	// Set up query result - user exists
	rows := sqlmock.NewRows([]string{"exists"}).AddRow(true)

	// Expected query with placeholder for the username (case-insensitive for PostgreSQL)
	mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM users WHERE LOWER\\(username\\) = LOWER\\(\\$1\\)\\)").
		WithArgs(username).
		WillReturnRows(rows)

	// Execute the method being tested
	exists, err := repo.ExistsByUsername(context.Background(), username)

	// Assert the results
	assert.NoError(t, err)
	assert.True(t, exists)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ExistsByUsername_DatabaseError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	username := "testuser"

	// Mock a database error
	dbErr := errors.New("database connection error")
	mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM users WHERE LOWER\\(username\\) = LOWER\\(\\$1\\)\\)").
		WithArgs(username).
		WillReturnError(dbErr)

	// Execute the method being tested
	exists, err := repo.ExistsByUsername(context.Background(), username)

	// Assert the results
	assert.Error(t, err)
	assert.False(t, exists)
	assert.Contains(t, err.Error(), "failed to check if username exists")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ExistsByUsername_NotExists(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	username := "nonexistentuser"

	// Set up query result - user doesn't exist
	rows := sqlmock.NewRows([]string{"exists"}).AddRow(false)

	// Expected query with placeholder for the username (case-insensitive for PostgreSQL)
	mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM users WHERE LOWER\\(username\\) = LOWER\\(\\$1\\)\\)").
		WithArgs(username).
		WillReturnRows(rows)

	// Execute the method being tested
	exists, err := repo.ExistsByUsername(context.Background(), username)

	// Assert the results
	assert.NoError(t, err)
	assert.False(t, exists)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ExistsByEmail(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	email := "existing@example.com"

	// Set up query result - email exists
	rows := sqlmock.NewRows([]string{"exists"}).AddRow(true)

	// Expected query with placeholder for the email (case-insensitive for PostgreSQL)
	mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM users WHERE LOWER\\(email\\) = LOWER\\(\\$1\\)\\)").
		WithArgs(email).
		WillReturnRows(rows)

	// Execute the method being tested
	exists, err := repo.ExistsByEmail(context.Background(), email)

	// Assert the results
	assert.NoError(t, err)
	assert.True(t, exists)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ExistsByEmail_DatabaseError(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	email := "test@example.com"

	// Mock a database error
	dbErr := errors.New("database connection error")
	mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM users WHERE LOWER\\(email\\) = LOWER\\(\\$1\\)\\)").
		WithArgs(email).
		WillReturnError(dbErr)

	// Execute the method being tested
	exists, err := repo.ExistsByEmail(context.Background(), email)

	// Assert the results
	assert.Error(t, err)
	assert.False(t, exists)
	assert.Contains(t, err.Error(), "failed to check if email exists")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ExistsByEmail_NotExists(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	email := "nonexistent@example.com"

	// Set up query result - email doesn't exist
	rows := sqlmock.NewRows([]string{"exists"}).AddRow(false)

	// Expected query with placeholder for the email (case-insensitive for PostgreSQL)
	mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM users WHERE LOWER\\(email\\) = LOWER\\(\\$1\\)\\)").
		WithArgs(email).
		WillReturnRows(rows)

	// Execute the method being tested
	exists, err := repo.ExistsByEmail(context.Background(), email)

	// Assert the results
	assert.NoError(t, err)
	assert.False(t, exists)
	assert.NoError(t, mock.ExpectationsWereMet())
}
