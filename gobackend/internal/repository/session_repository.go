package repository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// SessionRepository defines methods for interacting with sessions
type SessionRepository interface {
	Create(ctx context.Context, session *models.Session) error
	GetByID(ctx context.Context, id string) (*models.Session, error)
	GetByJWTID(ctx context.Context, jwtID string) (*models.Session, error)
	GetActiveByUserID(ctx context.Context, userID int64) ([]*models.Session, error)
	Delete(ctx context.Context, id string) error
	DeleteByJWTID(ctx context.Context, jwtID string) error
	DeleteByUserID(ctx context.Context, userID int64) error
	DeleteExpired(ctx context.Context) (int64, error)
	IsValidSession(ctx context.Context, jwtID string) (bool, error)
}

// MysqlSessionRepository is a MySQL implementation of SessionRepository
type MysqlSessionRepository struct {
	db *database.Pool
}

// NewSessionRepository creates a new SessionRepository
func NewSessionRepository(db *database.Pool) SessionRepository {
	return &MysqlSessionRepository{
		db: db,
	}
}

// Create adds a new session to the database
func (r *MysqlSessionRepository) Create(ctx context.Context, session *models.Session) error {
	// Start query timer
	startTime := time.Now()

	// Generate a unique ID if not already set
	if session.ID == "" {
		session.ID = uuid.New().String()
	}

	// Define the query
	query := `
		INSERT INTO sessions (session_id, user_id, jwt_id, expires_at, created_at)
		VALUES (?, ?, ?, ?, ?)
	`

	// Execute the query
	_, err := r.db.ExecContext(
		ctx,
		query,
		session.ID,
		session.UserID,
		session.JWTID,
		session.ExpiresAt,
		session.CreatedAt,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{session.ID, session.UserID, session.JWTID, session.ExpiresAt, session.CreatedAt},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to create session: %w", err)
	}

	log.Info().
		Str("session_id", session.ID).
		Int64("user_id", session.UserID).
		Str("jwt_id", session.JWTID).
		Time("expires_at", session.ExpiresAt).
		Msg("Session created")

	return nil
}

// GetByID retrieves a session by ID
func (r *MysqlSessionRepository) GetByID(ctx context.Context, id string) (*models.Session, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT session_id, user_id, jwt_id, expires_at, created_at
		FROM sessions
		WHERE session_id = ?
	`

	// Execute the query
	session := &models.Session{}
	err := r.db.QueryRowContext(ctx, query, id).Scan(
		&session.ID,
		&session.UserID,
		&session.JWTID,
		&session.ExpiresAt,
		&session.CreatedAt,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{id},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewNotFoundError("Session", id)
		}
		return nil, fmt.Errorf("failed to get session by ID: %w", err)
	}

	return session, nil
}

// GetByJWTID retrieves a session by JWT ID
func (r *MysqlSessionRepository) GetByJWTID(ctx context.Context, jwtID string) (*models.Session, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT session_id, user_id, jwt_id, expires_at, created_at
		FROM sessions
		WHERE jwt_id = ?
	`

	// Execute the query
	session := &models.Session{}
	err := r.db.QueryRowContext(ctx, query, jwtID).Scan(
		&session.ID,
		&session.UserID,
		&session.JWTID,
		&session.ExpiresAt,
		&session.CreatedAt,
	)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{jwtID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, utils.NewNotFoundError("Session", fmt.Sprintf("jwt_id=%s", jwtID))
		}
		return nil, fmt.Errorf("failed to get session by JWT ID: %w", err)
	}

	return session, nil
}

// GetActiveByUserID retrieves all active sessions for a user
func (r *MysqlSessionRepository) GetActiveByUserID(ctx context.Context, userID int64) ([]*models.Session, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT session_id, user_id, jwt_id, expires_at, created_at
		FROM sessions
		WHERE user_id = ? AND expires_at > ?
		ORDER BY created_at DESC
	`

	// Execute the query
	now := time.Now()
	rows, err := r.db.QueryContext(ctx, query, userID, now)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{userID, now},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return nil, fmt.Errorf("failed to get active sessions by user ID: %w", err)
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	// Parse the results
	var sessions []*models.Session
	for rows.Next() {
		session := &models.Session{}
		err := rows.Scan(
			&session.ID,
			&session.UserID,
			&session.JWTID,
			&session.ExpiresAt,
			&session.CreatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan session row: %w", err)
		}
		sessions = append(sessions, session)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating session rows: %w", err)
	}

	return sessions, nil
}

// Delete removes a session from the database
func (r *MysqlSessionRepository) Delete(ctx context.Context, id string) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM sessions WHERE session_id = ?`

	// Execute the query
	result, err := r.db.ExecContext(ctx, query, id)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{id},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to delete session: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("Session", id)
	}

	log.Info().
		Str("session_id", id).
		Msg("Session deleted")

	return nil
}

// DeleteByJWTID removes a session by JWT ID
func (r *MysqlSessionRepository) DeleteByJWTID(ctx context.Context, jwtID string) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM sessions WHERE jwt_id = ?`

	// Execute the query
	result, err := r.db.ExecContext(ctx, query, jwtID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{jwtID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to delete session by JWT ID: %w", err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return utils.NewNotFoundError("Session", fmt.Sprintf("jwt_id=%s", jwtID))
	}

	log.Info().
		Str("jwt_id", jwtID).
		Msg("Session deleted by JWT ID")

	return nil
}

// DeleteByUserID removes all sessions for a user
func (r *MysqlSessionRepository) DeleteByUserID(ctx context.Context, userID int64) error {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM sessions WHERE user_id = ?`

	// Execute the query
	result, err := r.db.ExecContext(ctx, query, userID)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{userID},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return fmt.Errorf("failed to delete sessions by user ID: %w", err)
	}

	// Log the deletion
	rowsAffected, _ := result.RowsAffected()
	log.Info().
		Int64("user_id", userID).
		Int64("count", rowsAffected).
		Msg("Sessions deleted for user")

	return nil
}

// DeleteExpired removes all expired sessions
func (r *MysqlSessionRepository) DeleteExpired(ctx context.Context) (int64, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `DELETE FROM sessions WHERE expires_at < ?`

	// Execute the query
	now := time.Now()
	result, err := r.db.ExecContext(ctx, query, now)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{now},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return 0, fmt.Errorf("failed to delete expired sessions: %w", err)
	}

	// Log the deletion
	count, err := result.RowsAffected()
	if err != nil {
		return 0, fmt.Errorf("failed to get rows affected: %w", err)
	}

	log.Info().
		Int64("count", count).
		Msg("Expired sessions deleted")

	return count, nil
}

// IsValidSession checks if a session with the given JWT ID exists and is not expired
func (r *MysqlSessionRepository) IsValidSession(ctx context.Context, jwtID string) (bool, error) {
	// Start query timer
	startTime := time.Now()

	// Define the query
	query := `
		SELECT EXISTS(
			SELECT 1 FROM sessions 
			WHERE jwt_id = ? AND expires_at > ?
		)
	`

	// Execute the query
	now := time.Now()
	var valid bool
	err := r.db.QueryRowContext(ctx, query, jwtID, now).Scan(&valid)

	// Log the query execution
	utils.LogDBQuery(
		query,
		[]interface{}{jwtID, now},
		time.Since(startTime),
		err,
	)

	if err != nil {
		return false, fmt.Errorf("failed to check session validity: %w", err)
	}

	return valid, nil
}
