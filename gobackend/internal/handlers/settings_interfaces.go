package handlers

import (
	"context"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

// SettingsServiceInterface defines methods required from SettingsService
type SettingsServiceInterface interface {
	GetUserSettings(ctx context.Context, userID int64) (*models.UserSetting, error)
	UpdateUserSettings(ctx context.Context, userID int64, update *models.UserSettingsUpdate) (*models.UserSetting, error)
	GetBanList(ctx context.Context, userID int64) (*models.BanListWithWords, error)
	AddBanListWords(ctx context.Context, userID int64, words []string) error
	RemoveBanListWords(ctx context.Context, userID int64, words []string) error
	GetSearchPatterns(ctx context.Context, userID int64) ([]*models.SearchPattern, error)
	CreateSearchPattern(ctx context.Context, userID int64, pattern *models.SearchPatternCreate) (*models.SearchPattern, error)
	UpdateSearchPattern(ctx context.Context, userID int64, patternID int64, update *models.SearchPatternUpdate) (*models.SearchPattern, error)
	DeleteSearchPattern(ctx context.Context, userID int64, patternID int64) error
	GetModelEntities(ctx context.Context, userID int64, methodID int64) ([]*models.ModelEntityWithMethod, error)
	AddModelEntities(ctx context.Context, userID int64, batch *models.ModelEntityBatch) ([]*models.ModelEntity, error)
	DeleteModelEntity(ctx context.Context, userID int64, entityID int64) error
	DeleteModelEntityByMethodID(ctx context.Context, userID int64, methodID int64) error

	ExportSettings(ctx context.Context, userID int64) (*models.SettingsExport, error)
	ImportSettings(ctx context.Context, userID int64, importData *models.SettingsExport) error
}
