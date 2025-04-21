package handlers

import (
	"context"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

// UserServiceInterface defines the methods required from UserService
type UserServiceInterface interface {
	GetUserByID(ctx context.Context, id int64) (*models.User, error)
	UpdateUser(ctx context.Context, id int64, update *models.UserUpdate) (*models.User, error)
	ChangePassword(ctx context.Context, id int64, newPassword string) error
	DeleteUser(ctx context.Context, id int64) error
	CheckUsername(ctx context.Context, username string) (bool, error)
	CheckEmail(ctx context.Context, email string) (bool, error)
	GetUserActiveSessions(ctx context.Context, userID int64) ([]*models.ActiveSessionInfo, error)
	InvalidateSession(ctx context.Context, userID int64, sessionID string) error
}
