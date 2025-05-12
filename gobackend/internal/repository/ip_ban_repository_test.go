package repository

import (
	"context"
	_ "database/sql"
	"errors"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// setupDBMock creates a new mock database and pool for testing
func setupDBMock(t *testing.T) (*database.Pool, sqlmock.Sqlmock, func()) {
	db, mock, err := sqlmock.New()
	require.NoError(t, err, "Failed to create mock database")

	pool := &database.Pool{
		DB: db,
	}

	return pool, mock, func() {
		db.Close()
	}
}

func TestNewIPBanRepository(t *testing.T) {
	// Arrange
	pool, _, cleanup := setupDBMock(t)
	defer cleanup()

	// Act
	repo := NewIPBanRepository(pool)

	// Assert
	assert.NotNil(t, repo, "Repository should not be nil")
	assert.Implements(t, (*IPBanRepository)(nil), repo, "Should implement IPBanRepository interface")
}

func TestCreate(t *testing.T) {
	t.Run("Success", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		now := time.Now()
		expiry := now.Add(24 * time.Hour)
		ban := &models.IPBan{
			IPAddress: "192.168.1.1",
			Reason:    "Test ban",
			ExpiresAt: &expiry,
			CreatedAt: now,
			CreatedBy: "admin",
		}

		expectedID := int64(1)
		mock.ExpectQuery("INSERT INTO ip_bans").
			WithArgs(ban.IPAddress, ban.Reason, ban.ExpiresAt, ban.CreatedAt, ban.CreatedBy).
			WillReturnRows(sqlmock.NewRows([]string{"ban_id"}).AddRow(expectedID))

		// Act
		result, err := repo.Create(ctx, ban)

		// Assert
		assert.NoError(t, err)
		assert.Equal(t, expectedID, result.ID)
		assert.Equal(t, ban.IPAddress, result.IPAddress)
		assert.Equal(t, ban.Reason, result.Reason)
		assert.Equal(t, ban.ExpiresAt, result.ExpiresAt)
		assert.Equal(t, ban.CreatedAt, result.CreatedAt)
		assert.Equal(t, ban.CreatedBy, result.CreatedBy)
		assert.NoError(t, mock.ExpectationsWereMet())
	})

	t.Run("Database Error", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		now := time.Now()
		ban := &models.IPBan{
			IPAddress: "192.168.1.1",
			Reason:    "Test ban",
			ExpiresAt: nil, // Test with nil expiry (permanent ban)
			CreatedAt: now,
			CreatedBy: "admin",
		}

		dbError := errors.New("database error")
		mock.ExpectQuery("INSERT INTO ip_bans").
			WithArgs(ban.IPAddress, ban.Reason, ban.ExpiresAt, ban.CreatedAt, ban.CreatedBy).
			WillReturnError(dbError)

		// Act
		result, err := repo.Create(ctx, ban)

		// Assert
		assert.Error(t, err)
		assert.Nil(t, result)
		assert.Contains(t, err.Error(), "failed to create IP ban")
		assert.NoError(t, mock.ExpectationsWereMet())
	})
}

func TestGetAll(t *testing.T) {
	t.Run("Success With Results", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		now := time.Now()
		expiry := now.Add(24 * time.Hour)

		rows := sqlmock.NewRows([]string{"ban_id", "ip_address", "reason", "expires_at", "created_at", "created_by"}).
			AddRow(1, "192.168.1.1", "Reason 1", expiry, now, "admin1").
			AddRow(2, "192.168.1.2", "Reason 2", nil, now, "admin2")

		mock.ExpectQuery("SELECT ban_id, ip_address, reason, expires_at, created_at, created_by FROM ip_bans").
			WithArgs(sqlmock.AnyArg()). // Current time for expiry check
			WillReturnRows(rows)

		// Act
		results, err := repo.GetAll(ctx)

		// Assert
		assert.NoError(t, err)
		assert.Len(t, results, 2)
		assert.Equal(t, int64(1), results[0].ID)
		assert.Equal(t, "192.168.1.1", results[0].IPAddress)
		assert.Equal(t, "Reason 1", results[0].Reason)
		assert.Equal(t, expiry.Truncate(time.Second), results[0].ExpiresAt.Truncate(time.Second))
		assert.Equal(t, now.Truncate(time.Second), results[0].CreatedAt.Truncate(time.Second))
		assert.Equal(t, "admin1", results[0].CreatedBy)

		assert.Equal(t, int64(2), results[1].ID)
		assert.Equal(t, "192.168.1.2", results[1].IPAddress)
		assert.Equal(t, "Reason 2", results[1].Reason)
		assert.Nil(t, results[1].ExpiresAt) // Permanent ban
		assert.NoError(t, mock.ExpectationsWereMet())
	})

	t.Run("Success With No Results", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()

		mock.ExpectQuery("SELECT ban_id, ip_address, reason, expires_at, created_at, created_by FROM ip_bans").
			WithArgs(sqlmock.AnyArg()). // Current time for expiry check
			WillReturnRows(sqlmock.NewRows([]string{"ban_id", "ip_address", "reason", "expires_at", "created_at", "created_by"}))

		// Act
		results, err := repo.GetAll(ctx)

		// Assert
		assert.NoError(t, err)
		assert.Empty(t, results)
		assert.NoError(t, mock.ExpectationsWereMet())
	})

	t.Run("Database Query Error", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		dbError := errors.New("query error")

		mock.ExpectQuery("SELECT ban_id, ip_address, reason, expires_at, created_at, created_by FROM ip_bans").
			WithArgs(sqlmock.AnyArg()). // Current time for expiry check
			WillReturnError(dbError)

		// Act
		results, err := repo.GetAll(ctx)

		// Assert
		assert.Error(t, err)
		assert.Nil(t, results)
		assert.Contains(t, err.Error(), "failed to query IP bans")
		assert.NoError(t, mock.ExpectationsWereMet())
	})

	t.Run("Row Scan Error", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		now := time.Now()

		// Returning a row with too few columns (missing created_by) to cause scan error
		rows := sqlmock.NewRows([]string{"ban_id", "ip_address", "reason", "expires_at", "created_at"}).
			AddRow(1, "192.168.1.1", "Reason 1", now.Add(24*time.Hour), now)

		mock.ExpectQuery("SELECT ban_id, ip_address, reason, expires_at, created_at, created_by FROM ip_bans").
			WithArgs(sqlmock.AnyArg()).
			WillReturnRows(rows)

		// Act
		results, err := repo.GetAll(ctx)

		// Assert
		assert.Error(t, err)
		assert.Nil(t, results)
		assert.Contains(t, err.Error(), "failed to scan IP ban row")
		assert.NoError(t, mock.ExpectationsWereMet())
	})
}

func TestGetByIP(t *testing.T) {
	t.Run("Success With Results", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		now := time.Now()
		expiry := now.Add(24 * time.Hour)
		ipAddress := "192.168.1.1"

		rows := sqlmock.NewRows([]string{"ban_id", "ip_address", "reason", "expires_at", "created_at", "created_by"}).
			AddRow(1, ipAddress, "Reason 1", expiry, now, "admin1")

		mock.ExpectQuery("SELECT ban_id, ip_address, reason, expires_at, created_at, created_by FROM ip_bans").
			WithArgs(ipAddress, sqlmock.AnyArg()). // IP and current time for expiry check
			WillReturnRows(rows)

		// Act
		results, err := repo.GetByIP(ctx, ipAddress)

		// Assert
		assert.NoError(t, err)
		assert.Len(t, results, 1)
		assert.Equal(t, int64(1), results[0].ID)
		assert.Equal(t, ipAddress, results[0].IPAddress)
		assert.Equal(t, "Reason 1", results[0].Reason)
		assert.Equal(t, expiry.Truncate(time.Second), results[0].ExpiresAt.Truncate(time.Second))
		assert.Equal(t, now.Truncate(time.Second), results[0].CreatedAt.Truncate(time.Second))
		assert.Equal(t, "admin1", results[0].CreatedBy)
		assert.NoError(t, mock.ExpectationsWereMet())
	})

	t.Run("Success With No Results", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		ipAddress := "192.168.1.1"

		mock.ExpectQuery("SELECT ban_id, ip_address, reason, expires_at, created_at, created_by FROM ip_bans").
			WithArgs(ipAddress, sqlmock.AnyArg()). // IP and current time for expiry check
			WillReturnRows(sqlmock.NewRows([]string{"ban_id", "ip_address", "reason", "expires_at", "created_at", "created_by"}))

		// Act
		results, err := repo.GetByIP(ctx, ipAddress)

		// Assert
		assert.NoError(t, err)
		assert.Empty(t, results)
		assert.NoError(t, mock.ExpectationsWereMet())
	})

	t.Run("Database Query Error", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		ipAddress := "192.168.1.1"
		dbError := errors.New("query error")

		mock.ExpectQuery("SELECT ban_id, ip_address, reason, expires_at, created_at, created_by FROM ip_bans").
			WithArgs(ipAddress, sqlmock.AnyArg()). // IP and current time for expiry check
			WillReturnError(dbError)

		// Act
		results, err := repo.GetByIP(ctx, ipAddress)

		// Assert
		assert.Error(t, err)
		assert.Nil(t, results)
		assert.Contains(t, err.Error(), "failed to query IP bans by IP")
		assert.NoError(t, mock.ExpectationsWereMet())
	})
}

func TestDelete(t *testing.T) {
	t.Run("Success", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		banID := int64(1)

		mock.ExpectExec("DELETE FROM ip_bans WHERE ban_id = \\$1").
			WithArgs(banID).
			WillReturnResult(sqlmock.NewResult(0, 1)) // 1 row affected

		// Act
		err := repo.Delete(ctx, banID)

		// Assert
		assert.NoError(t, err)
		assert.NoError(t, mock.ExpectationsWereMet())
	})

	t.Run("Ban Not Found", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		banID := int64(1)

		// Return 0 rows affected to simulate not found
		mock.ExpectExec("DELETE FROM ip_bans WHERE ban_id = \\$1").
			WithArgs(banID).
			WillReturnResult(sqlmock.NewResult(0, 0))

		// Act
		err := repo.Delete(ctx, banID)

		// Assert
		assert.Error(t, err)
		assert.True(t, utils.IsNotFoundError(err), "Should return a NotFoundError")
		assert.NoError(t, mock.ExpectationsWereMet())
	})

	t.Run("Database Error", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		banID := int64(1)
		dbError := errors.New("database error")

		mock.ExpectExec("DELETE FROM ip_bans WHERE ban_id = \\$1").
			WithArgs(banID).
			WillReturnError(dbError)

		// Act
		err := repo.Delete(ctx, banID)

		// Assert
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "failed to delete IP ban")
		assert.NoError(t, mock.ExpectationsWereMet())
	})

	t.Run("Error Getting Rows Affected", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		banID := int64(1)
		rowsError := errors.New("rows affected error")

		// Create a custom result that returns an error on RowsAffected
		result := sqlmock.NewErrorResult(rowsError)
		mock.ExpectExec("DELETE FROM ip_bans WHERE ban_id = \\$1").
			WithArgs(banID).
			WillReturnResult(result)

		// Act
		err := repo.Delete(ctx, banID)

		// Assert
		assert.Error(t, err)
		assert.Contains(t, err.Error(), "failed to get rows affected")
		assert.NoError(t, mock.ExpectationsWereMet())
	})
}

func TestDeleteExpired(t *testing.T) {
	t.Run("Success With Deleted Rows", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		deletedRows := int64(5)

		mock.ExpectExec("DELETE FROM ip_bans WHERE expires_at < \\$1").
			WithArgs(sqlmock.AnyArg()). // Current time
			WillReturnResult(sqlmock.NewResult(0, deletedRows))

		// Act
		count, err := repo.DeleteExpired(ctx)

		// Assert
		assert.NoError(t, err)
		assert.Equal(t, deletedRows, count)
		assert.NoError(t, mock.ExpectationsWereMet())
	})

	t.Run("Success With No Deleted Rows", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()

		mock.ExpectExec("DELETE FROM ip_bans WHERE expires_at < \\$1").
			WithArgs(sqlmock.AnyArg()). // Current time
			WillReturnResult(sqlmock.NewResult(0, 0))

		// Act
		count, err := repo.DeleteExpired(ctx)

		// Assert
		assert.NoError(t, err)
		assert.Equal(t, int64(0), count)
		assert.NoError(t, mock.ExpectationsWereMet())
	})

	t.Run("Database Error", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		dbError := errors.New("database error")

		mock.ExpectExec("DELETE FROM ip_bans WHERE expires_at < \\$1").
			WithArgs(sqlmock.AnyArg()). // Current time
			WillReturnError(dbError)

		// Act
		count, err := repo.DeleteExpired(ctx)

		// Assert
		assert.Error(t, err)
		assert.Equal(t, int64(0), count)
		assert.Contains(t, err.Error(), "failed to delete expired IP bans")
		assert.NoError(t, mock.ExpectationsWereMet())
	})

	t.Run("Error Getting Rows Affected", func(t *testing.T) {
		// Arrange
		pool, mock, cleanup := setupDBMock(t)
		defer cleanup()
		repo := NewIPBanRepository(pool)

		ctx := context.Background()
		rowsError := errors.New("rows affected error")

		// Create a custom result that returns an error on RowsAffected
		result := sqlmock.NewErrorResult(rowsError)
		mock.ExpectExec("DELETE FROM ip_bans WHERE expires_at < \\$1").
			WithArgs(sqlmock.AnyArg()). // Current time
			WillReturnResult(result)

		// Act
		count, err := repo.DeleteExpired(ctx)

		// Assert
		assert.Error(t, err)
		assert.Equal(t, int64(0), count)
		assert.Contains(t, err.Error(), "failed to get rows affected")
		assert.NoError(t, mock.ExpectationsWereMet())
	})
}
