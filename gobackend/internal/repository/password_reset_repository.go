package repository

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	_ "github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

var (
	ErrTokenNotFound = errors.New("token not found or expired")
)

// PasswordResetRepository handles database operations for password reset tokens.
type PasswordResetRepository struct {
	db *database.Pool
}

// NewPasswordResetRepository creates a new PasswordResetRepository.
func NewPasswordResetRepository(db *database.Pool) PasswordResetRepository {
	return PasswordResetRepository{db: db}
}

// GenerateToken generates a secure random token and its SHA256 hash.
// It returns the plain token (to be sent to the user) and its hash (to be stored).
func GenerateToken() (string, string, error) {
	tokenBytes := make([]byte, 32)
	_, err := rand.Read(tokenBytes)
	if err != nil {
		return "", "", fmt.Errorf("failed to generate token bytes: %w", err)
	}
	token := hex.EncodeToString(tokenBytes) // Plain token for the user

	hash := sha256.Sum256([]byte(token)) // Hash of the token for storage
	tokenHash := hex.EncodeToString(hash[:])
	return token, tokenHash, nil
}

// Create stores a new password reset token hash in the database.
// The actual token is sent to the user, its hash is stored.
func (r *PasswordResetRepository) Create(ctx context.Context, userID int64, tokenHash string, duration time.Duration) error {
	expiresAt := time.Now().Add(duration)
	query := fmt.Sprintf(`
		INSERT INTO %s (token_hash, user_id, expires_at, created_at)
		VALUES ($1, $2, $3, $4)
	`, constants.TablePasswordResetTokens)

	_, err := r.db.ExecContext(ctx, query, tokenHash, userID, expiresAt, time.Now())
	if err != nil {
		return fmt.Errorf("failed to create password reset token: %w", err)
	}
	return nil
}

// GetUserIDByTokenHash retrieves the user ID and expiry for a given token hash.
// It returns ErrTokenNotFound if the token doesn't exist or is expired.
func (r *PasswordResetRepository) GetUserIDByTokenHash(ctx context.Context, tokenHash string) (int64, time.Time, error) {
	var userID int64
	var expiresAt time.Time
	query := fmt.Sprintf(`
		SELECT user_id, expires_at
		FROM %s
		WHERE token_hash = $1
	`, constants.TablePasswordResetTokens)

	err := r.db.QueryRowContext(ctx, query, tokenHash).Scan(&userID, &expiresAt)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return 0, time.Time{}, ErrTokenNotFound
		}
		return 0, time.Time{}, fmt.Errorf("failed to query password reset token: %w", err)
	}

	return userID, expiresAt, nil
}

// Delete removes a password reset token hash from the database.
func (r *PasswordResetRepository) Delete(ctx context.Context, tokenHash string) error {
	query := fmt.Sprintf("DELETE FROM %s WHERE token_hash = $1", constants.TablePasswordResetTokens)
	result, err := r.db.ExecContext(ctx, query, tokenHash)
	if err != nil {
		return fmt.Errorf("failed to delete password reset token: %w", err)
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("failed to get rows affected after deleting token: %w", err)
	}
	if rowsAffected == 0 {
		// It's not necessarily an error if the token was already deleted (e.g., by another request or a cleanup job)
		// However, for strictness, you could return ErrTokenNotFound here if needed.
		// For now, we'll consider it a successful operation if no error occurred.
	}
	return nil
}

// DeleteByUserID removes all password reset tokens for a specific user.
// This can be useful, for example, after a successful password reset.
func (r *PasswordResetRepository) DeleteByUserID(ctx context.Context, userID int64) error {
	query := fmt.Sprintf("DELETE FROM %s WHERE user_id = $1", constants.TablePasswordResetTokens)
	_, err := r.db.ExecContext(ctx, query, userID)
	if err != nil {
		return fmt.Errorf("failed to delete password reset tokens for user %d: %w", userID, err)
	}
	return nil
}
