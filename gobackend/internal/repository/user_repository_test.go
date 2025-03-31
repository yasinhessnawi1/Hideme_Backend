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

// setupUserRepositoryTest creates a new test database connection and mock
func setupUserRepositoryTest(t *testing.T) (*repository.MysqlUserRepository, sqlmock.Sqlmock, func()) {
	// Create a new SQL mock database
	db, mock, err := sqlmock.New()
	require.NoError(t, err)

	// Create a database pool with the mock database
	dbPool := &database.Pool{DB: db}

	// Create a new repository with the mocked database
	repo := repository.NewUserRepository(dbPool).(*repository.MysqlUserRepository)

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
	now := time.Now()
	user := &models.User{
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	// Expected query with placeholders for the arguments
	mock.ExpectExec("INSERT INTO users").
		WithArgs(user.Username, user.Email, user.PasswordHash, user.Salt, user.CreatedAt, user.UpdatedAt).
		WillReturnResult(sqlmock.NewResult(1, 1))

	// Execute the method being tested
	err := repo.Create(context.Background(), user)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(1), user.ID) // ID should be set from LastInsertId
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_Create_DuplicateUsername(t *testing.T) {

}

func TestUserRepository_Create_DuplicateEmail(t *testing.T) {

}

func TestUserRepository_GetByID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(1)
	now := time.Now()
	user := &models.User{
		ID:           id,
		Username:     "testuser",
		Email:        "test@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"user_id", "username", "email", "password_hash", "salt", "created_at", "updated_at"}).
		AddRow(user.ID, user.Username, user.Email, user.PasswordHash, user.Salt, user.CreatedAt, user.UpdatedAt)

	// Expected query with placeholder for the ID
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, created_at, updated_at FROM users WHERE user_id = ?").
		WithArgs(id).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

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

func TestUserRepository_GetByID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := int64(999)

	// Mock database response - empty result
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, created_at, updated_at FROM users WHERE user_id = ?").
		WithArgs(id).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_GetByUsername(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	username := "testuser"
	now := time.Now()
	user := &models.User{
		ID:           1,
		Username:     username,
		Email:        "test@example.com",
		PasswordHash: "hashed_password",
		Salt:         "salt_value",
		CreatedAt:    now,
		UpdatedAt:    now,
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"user_id", "username", "email", "password_hash", "salt", "created_at", "updated_at"}).
		AddRow(user.ID, user.Username, user.Email, user.PasswordHash, user.Salt, user.CreatedAt, user.UpdatedAt)

	// Expected query with placeholder for the username (case-insensitive)
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, created_at, updated_at FROM users WHERE LOWER\\(username\\) = LOWER\\(\\?\\)").
		WithArgs(username).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByUsername(context.Background(), username)

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

func TestUserRepository_GetByUsername_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	username := "nonexistent"

	// Mock database response - empty result
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, created_at, updated_at FROM users WHERE LOWER\\(username\\) = LOWER\\(\\?\\)").
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

	// Expected query with placeholder for the email (case-insensitive)
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, created_at, updated_at FROM users WHERE LOWER\\(email\\) = LOWER\\(\\?\\)").
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

func TestUserRepository_GetByEmail_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	email := "nonexistent@example.com"

	// Mock database response - empty result
	mock.ExpectQuery("SELECT user_id, username, email, password_hash, salt, created_at, updated_at FROM users WHERE LOWER\\(email\\) = LOWER\\(\\?\\)").
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
	mock.ExpectExec("UPDATE users SET username = \\?, email = \\?, updated_at = \\? WHERE user_id = \\?").
		WithArgs(user.Username, user.Email, user.UpdatedAt, user.ID).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.Update(context.Background(), user)

	// Assert the results
	assert.NoError(t, err)
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

	// Mock a duplicate key error for username
	duplicateErr := errors.New("Error 1062: Duplicate entry 'duplicateuser' for key 'username'")
	mock.ExpectExec("UPDATE users SET username = \\?, email = \\?, updated_at = \\? WHERE user_id = \\?").
		WithArgs(user.Username, user.Email, user.UpdatedAt, user.ID).
		WillReturnError(duplicateErr)

	// Execute the method being tested
	err := repo.Update(context.Background(), user)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "duplicate")
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
	mock.ExpectExec("UPDATE users SET username = \\?, email = \\?, updated_at = \\? WHERE user_id = \\?").
		WithArgs(user.Username, user.Email, user.UpdatedAt, user.ID).
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
	mock.ExpectExec("DELETE FROM users WHERE user_id = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectCommit()

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
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
	mock.ExpectExec("DELETE FROM users WHERE user_id = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectRollback()

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
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
	mock.ExpectExec("UPDATE users SET password_hash = \\?, salt = \\?, updated_at = \\? WHERE user_id = \\?").
		WithArgs(passwordHash, salt, sqlmock.AnyArg(), id).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.ChangePassword(context.Background(), id, passwordHash, salt)

	// Assert the results
	assert.NoError(t, err)
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
	mock.ExpectExec("UPDATE users SET password_hash = \\?, salt = \\?, updated_at = \\? WHERE user_id = \\?").
		WithArgs(passwordHash, salt, sqlmock.AnyArg(), id).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.ChangePassword(context.Background(), id, passwordHash, salt)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ExistsByUsername(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	username := "existinguser"

	// Set up query result - user exists
	rows := sqlmock.NewRows([]string{"exists"}).AddRow(1)

	// Expected query with placeholder for the username (case-insensitive)
	mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM users WHERE LOWER\\(username\\) = LOWER\\(\\?\\)\\)").
		WithArgs(username).
		WillReturnRows(rows)

	// Execute the method being tested
	exists, err := repo.ExistsByUsername(context.Background(), username)

	// Assert the results
	assert.NoError(t, err)
	assert.True(t, exists)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ExistsByUsername_NotExists(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	username := "nonexistentuser"

	// Set up query result - user doesn't exist
	rows := sqlmock.NewRows([]string{"exists"}).AddRow(0)

	// Expected query with placeholder for the username (case-insensitive)
	mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM users WHERE LOWER\\(username\\) = LOWER\\(\\?\\)\\)").
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
	rows := sqlmock.NewRows([]string{"exists"}).AddRow(1)

	// Expected query with placeholder for the email (case-insensitive)
	mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM users WHERE LOWER\\(email\\) = LOWER\\(\\?\\)\\)").
		WithArgs(email).
		WillReturnRows(rows)

	// Execute the method being tested
	exists, err := repo.ExistsByEmail(context.Background(), email)

	// Assert the results
	assert.NoError(t, err)
	assert.True(t, exists)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestUserRepository_ExistsByEmail_NotExists(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupUserRepositoryTest(t)
	defer cleanup()

	// Set up test data
	email := "nonexistent@example.com"

	// Set up query result - email doesn't exist
	rows := sqlmock.NewRows([]string{"exists"}).AddRow(0)

	// Expected query with placeholder for the email (case-insensitive)
	mock.ExpectQuery("SELECT EXISTS\\(SELECT 1 FROM users WHERE LOWER\\(email\\) = LOWER\\(\\?\\)\\)").
		WithArgs(email).
		WillReturnRows(rows)

	// Execute the method being tested
	exists, err := repo.ExistsByEmail(context.Background(), email)

	// Assert the results
	assert.NoError(t, err)
	assert.False(t, exists)
	assert.NoError(t, mock.ExpectationsWereMet())
}
