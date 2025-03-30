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

// setupAPIKeyRepositoryTest creates a new test database connection and mock
func setupAPIKeyRepositoryTest(t *testing.T) (*repository.MysqlAPIKeyRepository, sqlmock.Sqlmock, func()) {
	// Create a new SQL mock database
	db, mock, err := sqlmock.New()
	require.NoError(t, err)

	// Create a database pool with the mock database
	dbPool := &database.Pool{DB: db}

	// Create a new repository with the mocked database
	repo := repository.NewAPIKeyRepository(dbPool).(*repository.MysqlAPIKeyRepository)

	// Return the repository, mock and a cleanup function
	return repo, mock, func() {
		db.Close()
	}
}

func TestAPIKeyRepository_Create(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupAPIKeyRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	apiKey := &models.APIKey{
		ID:         "test-key-id",
		UserID:     100,
		APIKeyHash: "hashed-api-key",
		Name:       "Test API Key",
		ExpiresAt:  now.Add(24 * time.Hour),
		CreatedAt:  now,
	}

	// Expected query with placeholders for the arguments
	mock.ExpectExec("INSERT INTO api_keys").
		WithArgs(apiKey.ID, apiKey.UserID, apiKey.APIKeyHash, apiKey.Name, apiKey.ExpiresAt, apiKey.CreatedAt).
		WillReturnResult(sqlmock.NewResult(1, 1))

	// Execute the method being tested
	err := repo.Create(context.Background(), apiKey)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestAPIKeyRepository_Create_Error(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupAPIKeyRepositoryTest(t)
	defer cleanup()

	// Set up test data
	now := time.Now()
	apiKey := &models.APIKey{
		ID:         "test-key-id",
		UserID:     100,
		APIKeyHash: "hashed-api-key",
		Name:       "Test API Key",
		ExpiresAt:  now.Add(24 * time.Hour),
		CreatedAt:  now,
	}

	// Mock database error
	mock.ExpectExec("INSERT INTO api_keys").
		WithArgs(apiKey.ID, apiKey.UserID, apiKey.APIKeyHash, apiKey.Name, apiKey.ExpiresAt, apiKey.CreatedAt).
		WillReturnError(errors.New("database error"))

	// Execute the method being tested
	err := repo.Create(context.Background(), apiKey)

	// Assert the results
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "failed to create API key")
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestAPIKeyRepository_GetByID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupAPIKeyRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := "test-key-id"
	now := time.Now()
	apiKey := &models.APIKey{
		ID:         id,
		UserID:     100,
		APIKeyHash: "hashed-api-key",
		Name:       "Test API Key",
		ExpiresAt:  now.Add(24 * time.Hour),
		CreatedAt:  now,
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"key_id", "user_id", "api_key_hash", "name", "expires_at", "created_at"}).
		AddRow(apiKey.ID, apiKey.UserID, apiKey.APIKeyHash, apiKey.Name, apiKey.ExpiresAt, apiKey.CreatedAt)

	// Expected query with placeholder for the ID
	mock.ExpectQuery("SELECT key_id, user_id, api_key_hash, name, expires_at, created_at FROM api_keys WHERE key_id = ?").
		WithArgs(id).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, apiKey.ID, result.ID)
	assert.Equal(t, apiKey.UserID, result.UserID)
	assert.Equal(t, apiKey.APIKeyHash, result.APIKeyHash)
	assert.Equal(t, apiKey.Name, result.Name)
	assert.WithinDuration(t, apiKey.ExpiresAt, result.ExpiresAt, time.Second)
	assert.WithinDuration(t, apiKey.CreatedAt, result.CreatedAt, time.Second)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestAPIKeyRepository_GetByID_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupAPIKeyRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := "nonexistent-id"

	// Mock database response - empty result
	mock.ExpectQuery("SELECT key_id, user_id, api_key_hash, name, expires_at, created_at FROM api_keys WHERE key_id = ?").
		WithArgs(id).
		WillReturnError(sql.ErrNoRows)

	// Execute the method being tested
	result, err := repo.GetByID(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestAPIKeyRepository_GetByUserID(t *testing.T) {

}

func TestAPIKeyRepository_VerifyKey(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupAPIKeyRepositoryTest(t)
	defer cleanup()

	// Set up test data
	keyID := "key-id"
	keyHash := "key-hash"
	now := time.Now()
	apiKey := &models.APIKey{
		ID:         keyID,
		UserID:     100,
		APIKeyHash: keyHash,
		Name:       "Test Key",
		ExpiresAt:  now.Add(24 * time.Hour),
		CreatedAt:  now,
	}

	// Set up query result
	rows := sqlmock.NewRows([]string{"key_id", "user_id", "api_key_hash", "name", "expires_at", "created_at"}).
		AddRow(apiKey.ID, apiKey.UserID, apiKey.APIKeyHash, apiKey.Name, apiKey.ExpiresAt, apiKey.CreatedAt)

	// Expected query with placeholders for key ID, hash, and time
	mock.ExpectQuery("SELECT key_id, user_id, api_key_hash, name, expires_at, created_at FROM api_keys WHERE key_id = \\? AND api_key_hash = \\? AND expires_at > \\?").
		WithArgs(keyID, keyHash, sqlmock.AnyArg()).
		WillReturnRows(rows)

	// Execute the method being tested
	result, err := repo.VerifyKey(context.Background(), keyID, keyHash)

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, apiKey.ID, result.ID)
	assert.Equal(t, apiKey.UserID, result.UserID)
	assert.Equal(t, apiKey.APIKeyHash, result.APIKeyHash)
	assert.Equal(t, apiKey.Name, result.Name)
	assert.WithinDuration(t, apiKey.ExpiresAt, result.ExpiresAt, time.Second)
	assert.WithinDuration(t, apiKey.CreatedAt, result.CreatedAt, time.Second)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestAPIKeyRepository_VerifyKey_Expired(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupAPIKeyRepositoryTest(t)
	defer cleanup()

	// Set up test data
	keyID := "key-id"
	keyHash := "key-hash"

	// Mock database response - no rows for valid key
	mock.ExpectQuery("SELECT key_id, user_id, api_key_hash, name, expires_at, created_at FROM api_keys WHERE key_id = \\? AND api_key_hash = \\? AND expires_at > \\?").
		WithArgs(keyID, keyHash, sqlmock.AnyArg()).
		WillReturnError(sql.ErrNoRows)

	// Mock the expiry check query
	expiredRows := sqlmock.NewRows([]string{"expires_at"}).
		AddRow(time.Now().Add(-time.Hour)) // Expired time

	mock.ExpectQuery("SELECT expires_at FROM api_keys WHERE key_id = \\?").
		WithArgs(keyID).
		WillReturnRows(expiredRows)

	// Execute the method being tested
	result, err := repo.VerifyKey(context.Background(), keyID, keyHash)

	// Assert the results
	assert.Error(t, err)
	assert.Nil(t, result)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestAPIKeyRepository_Delete(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupAPIKeyRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := "key-id"

	// Expected query with placeholder for the ID
	mock.ExpectExec("DELETE FROM api_keys WHERE key_id = \\?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestAPIKeyRepository_Delete_NotFound(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupAPIKeyRepositoryTest(t)
	defer cleanup()

	// Set up test data
	id := "nonexistent-id"

	// Expected query with placeholder for the ID, but no rows affected
	mock.ExpectExec("DELETE FROM api_keys WHERE key_id = \\?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Execute the method being tested
	err := repo.Delete(context.Background(), id)

	// Assert the results
	assert.Error(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestAPIKeyRepository_DeleteByUserID(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupAPIKeyRepositoryTest(t)
	defer cleanup()

	// Set up test data
	userID := int64(100)

	// Expected query with placeholder for the user ID
	mock.ExpectExec("DELETE FROM api_keys WHERE user_id = \\?").
		WithArgs(userID).
		WillReturnResult(sqlmock.NewResult(0, 3)) // 3 rows affected

	// Execute the method being tested
	err := repo.DeleteByUserID(context.Background(), userID)

	// Assert the results
	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestAPIKeyRepository_DeleteExpired(t *testing.T) {
	// Set up the test
	repo, mock, cleanup := setupAPIKeyRepositoryTest(t)
	defer cleanup()

	// Expected query with placeholder for current time
	mock.ExpectExec("DELETE FROM api_keys WHERE expires_at < \\?").
		WithArgs(sqlmock.AnyArg()).
		WillReturnResult(sqlmock.NewResult(0, 5)) // 5 expired keys deleted

	// Execute the method being tested
	count, err := repo.DeleteExpired(context.Background())

	// Assert the results
	assert.NoError(t, err)
	assert.Equal(t, int64(5), count)
	assert.NoError(t, mock.ExpectationsWereMet())
}
