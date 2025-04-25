// Package handlers provides HTTP request handlers for the HideMe API.
package handlers

import (
	"context"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

// SettingsServiceInterface defines methods required from the settings service.
// This interface is used by the settings handlers to interact with the settings business logic
// without being tightly coupled to the implementation.
type SettingsServiceInterface interface {
	// GetUserSettings retrieves the settings for a specific user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user whose settings to retrieve
	//
	// Returns:
	//   - The user's settings
	//   - An error if retrieval fails
	GetUserSettings(ctx context.Context, userID int64) (*models.UserSetting, error)

	// UpdateUserSettings updates the settings for a specific user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user whose settings to update
	//   - update: The settings values to update
	//
	// Returns:
	//   - The updated user settings
	//   - An error if the update fails
	UpdateUserSettings(ctx context.Context, userID int64, update *models.UserSettingsUpdate) (*models.UserSetting, error)

	// GetBanList retrieves the ban list for a specific user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user whose ban list to retrieve
	//
	// Returns:
	//   - The user's ban list with words
	//   - An error if retrieval fails
	GetBanList(ctx context.Context, userID int64) (*models.BanListWithWords, error)

	// AddBanListWords adds words to a user's ban list.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user whose ban list to update
	//   - words: The words to add to the ban list
	//
	// Returns:
	//   - An error if the operation fails
	AddBanListWords(ctx context.Context, userID int64, words []string) error

	// RemoveBanListWords removes words from a user's ban list.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user whose ban list to update
	//   - words: The words to remove from the ban list
	//
	// Returns:
	//   - An error if the operation fails
	RemoveBanListWords(ctx context.Context, userID int64, words []string) error

	// GetSearchPatterns retrieves the search patterns for a specific user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user whose search patterns to retrieve
	//
	// Returns:
	//   - The user's search patterns
	//   - An error if retrieval fails
	GetSearchPatterns(ctx context.Context, userID int64) ([]*models.SearchPattern, error)

	// CreateSearchPattern creates a new search pattern for a user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user to create the pattern for
	//   - pattern: The search pattern to create
	//
	// Returns:
	//   - The created search pattern
	//   - An error if creation fails
	CreateSearchPattern(ctx context.Context, userID int64, pattern *models.SearchPatternCreate) (*models.SearchPattern, error)

	// UpdateSearchPattern updates an existing search pattern.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user who owns the pattern
	//   - patternID: The ID of the pattern to update
	//   - update: The pattern values to update
	//
	// Returns:
	//   - The updated search pattern
	//   - An error if the update fails or pattern not found
	UpdateSearchPattern(ctx context.Context, userID int64, patternID int64, update *models.SearchPatternUpdate) (*models.SearchPattern, error)

	// DeleteSearchPattern deletes a search pattern.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user who owns the pattern
	//   - patternID: The ID of the pattern to delete
	//
	// Returns:
	//   - An error if the deletion fails or pattern not found
	DeleteSearchPattern(ctx context.Context, userID int64, patternID int64) error

	// GetModelEntities retrieves model entities for a specific method.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user who owns the entities
	//   - methodID: The ID of the method to get entities for
	//
	// Returns:
	//   - The model entities with method information
	//   - An error if retrieval fails
	GetModelEntities(ctx context.Context, userID int64, methodID int64) ([]*models.ModelEntityWithMethod, error)

	// AddModelEntities adds model entities for a user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user to add entities for
	//   - batch: The batch of entities to add
	//
	// Returns:
	//   - The added model entities
	//   - An error if the operation fails
	AddModelEntities(ctx context.Context, userID int64, batch *models.ModelEntityBatch) ([]*models.ModelEntity, error)

	// DeleteModelEntity deletes a model entity.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user who owns the entity
	//   - entityID: The ID of the entity to delete
	//
	// Returns:
	//   - An error if the deletion fails or entity not found
	DeleteModelEntity(ctx context.Context, userID int64, entityID int64) error

	// DeleteModelEntityByMethodID deletes all model entities for a specific method.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user who owns the entities
	//   - methodID: The ID of the method whose entities to delete
	//
	// Returns:
	//   - An error if the deletion fails
	DeleteModelEntityByMethodID(ctx context.Context, userID int64, methodID int64) error

	// ExportSettings exports all settings for a user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user whose settings to export
	//
	// Returns:
	//   - The complete settings export
	//   - An error if the export fails
	ExportSettings(ctx context.Context, userID int64) (*models.SettingsExport, error)

	// ImportSettings imports settings for a user.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - userID: The ID of the user to import settings for
	//   - importData: The settings data to import
	//
	// Returns:
	//   - An error if the import fails
	ImportSettings(ctx context.Context, userID int64, importData *models.SettingsExport) error
}
