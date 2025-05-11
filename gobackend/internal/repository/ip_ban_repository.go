// Package repository provides data access interfaces and implementations.
package repository

import (
	"context"
	"fmt"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// IPBanRepository defines methods for managing IP ban records.
type IPBanRepository interface {
	// Create adds a new IP ban record.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation
	//   - ban: The IP ban record to create
	//
	// Returns:
	//   - The created IP ban with ID populated
	//   - Error if the operation fails
	Create(ctx context.Context, ban *models.IPBan) (*models.IPBan, error)

	// GetAll retrieves all active IP bans.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation
	//
	// Returns:
	//   - A slice of all active IP bans
	//   - Error if the operation fails
	GetAll(ctx context.Context) ([]*models.IPBan, error)

	// GetByIP retrieves all active bans for a specific IP.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation
	//   - ip: The IP address to check
	//
	// Returns:
	//   - A slice of active bans that match the IP
	//   - Error if the operation fails
	GetByIP(ctx context.Context, ip string) ([]*models.IPBan, error)

	// Delete removes an IP ban by ID.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation
	//   - id: The ID of the ban to remove
	//
	// Returns:
	//   - Error if the operation fails
	Delete(ctx context.Context, id int64) error

	// DeleteExpired removes all expired IP bans.
	//
	// Parameters:
	//   - ctx: Context for transaction and cancellation
	//
	// Returns:
	//   - The number of bans removed
	//   - Error if the operation fails
	DeleteExpired(ctx context.Context) (int64, error)
}

// PostgresIPBanRepository is an implementation of IPBanRepository for PostgreSQL.
type PostgresIPBanRepository struct {
	db *database.Pool
}

// NewIPBanRepository creates a new IPBanRepository for PostgreSQL.
//
// Parameters:
//   - db: Database connection pool
//
// Returns:
//   - An implementation of IPBanRepository
func NewIPBanRepository(db *database.Pool) IPBanRepository {
	return &PostgresIPBanRepository{
		db: db,
	}
}

// Create adds a new IP ban record.
func (r *PostgresIPBanRepository) Create(ctx context.Context, ban *models.IPBan) (*models.IPBan, error) {
	query := `
		INSERT INTO ip_bans (ip_address, reason, expires_at, created_at, created_by)
		VALUES ($1, $2, $3, $4, $5)
		RETURNING ban_id
	`

	err := r.db.QueryRowContext(
		ctx,
		query,
		ban.IPAddress,
		ban.Reason,
		ban.ExpiresAt,
		ban.CreatedAt,
		ban.CreatedBy,
	).Scan(&ban.ID)

	if err != nil {
		return nil, fmt.Errorf("failed to create IP ban: %w", err)
	}

	return ban, nil
}

// GetAll retrieves all active IP bans.
func (r *PostgresIPBanRepository) GetAll(ctx context.Context) ([]*models.IPBan, error) {
	query := `
		SELECT ban_id, ip_address, reason, expires_at, created_at, created_by
		FROM ip_bans
		WHERE expires_at IS NULL OR expires_at > $1
		ORDER BY created_at DESC
	`

	rows, err := r.db.QueryContext(ctx, query, time.Now())
	if err != nil {
		return nil, fmt.Errorf("failed to query IP bans: %w", err)
	}
	defer rows.Close()

	var bans []*models.IPBan
	for rows.Next() {
		ban := &models.IPBan{}
		if err := rows.Scan(
			&ban.ID,
			&ban.IPAddress,
			&ban.Reason,
			&ban.ExpiresAt,
			&ban.CreatedAt,
			&ban.CreatedBy,
		); err != nil {
			return nil, fmt.Errorf("failed to scan IP ban row: %w", err)
		}
		bans = append(bans, ban)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating IP ban rows: %w", err)
	}

	return bans, nil
}

// GetByIP retrieves all active bans for a specific IP.
func (r *PostgresIPBanRepository) GetByIP(ctx context.Context, ip string) ([]*models.IPBan, error) {
	query := `
		SELECT ban_id, ip_address, reason, expires_at, created_at, created_by
		FROM ip_bans
		WHERE ip_address = $1 AND (expires_at IS NULL OR expires_at > $2)
	`

	rows, err := r.db.QueryContext(ctx, query, ip, time.Now())
	if err != nil {
		return nil, fmt.Errorf("failed to query IP bans by IP: %w", err)
	}
	defer rows.Close()

	var bans []*models.IPBan
	for rows.Next() {
		ban := &models.IPBan{}
		if err := rows.Scan(
			&ban.ID,
			&ban.IPAddress,
			&ban.Reason,
			&ban.ExpiresAt,
			&ban.CreatedAt,
			&ban.CreatedBy,
		); err != nil {
			return nil, fmt.Errorf("failed to scan IP ban row: %w", err)
		}
		bans = append(bans, ban)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating IP ban rows: %w", err)
	}

	return bans, nil
}

// Delete removes an IP ban by ID.
func (r *PostgresIPBanRepository) Delete(ctx context.Context, id int64) error {
	query := `DELETE FROM ip_bans WHERE ban_id = $1`

	result, err := r.db.ExecContext(ctx, query, id)
	if err != nil {
		return fmt.Errorf("failed to delete IP ban: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("IPBan", id)
	}

	return nil
}

// DeleteExpired removes all expired IP bans.
func (r *PostgresIPBanRepository) DeleteExpired(ctx context.Context) (int64, error) {
	query := `DELETE FROM ip_bans WHERE expires_at < $1`

	result, err := r.db.ExecContext(ctx, query, time.Now())
	if err != nil {
		return 0, fmt.Errorf("failed to delete expired IP bans: %w", err)
	}

	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("failed to get rows affected: %w", err)
	}

	return rowsAffected, nil
}
