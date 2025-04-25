package service

import (
	"context"
	"fmt"
	"time"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/repository"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// SettingsService handles user settings operations
type SettingsService struct {
	settingsRepo    repository.SettingsRepository
	banListRepo     repository.BanListRepository
	patternRepo     repository.PatternRepository
	modelEntityRepo repository.ModelEntityRepository
}

// NewSettingsService creates a new SettingsService
func NewSettingsService(
	settingsRepo repository.SettingsRepository,
	banListRepo repository.BanListRepository,
	patternRepo repository.PatternRepository,
	modelEntityRepo repository.ModelEntityRepository,
) *SettingsService {
	return &SettingsService{
		settingsRepo:    settingsRepo,
		banListRepo:     banListRepo,
		patternRepo:     patternRepo,
		modelEntityRepo: modelEntityRepo,
	}
}

// GetUserSettings retrieves settings for a user
func (s *SettingsService) GetUserSettings(ctx context.Context, userID int64) (*models.UserSetting, error) {
	// Get or create settings
	settings, err := s.settingsRepo.EnsureDefaultSettings(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("failed to get user settings: %w", err)
	}

	return settings, nil
}

// UpdateUserSettings updates settings for a user
func (s *SettingsService) UpdateUserSettings(ctx context.Context, userID int64, update *models.UserSettingsUpdate) (*models.UserSetting, error) {
	// Get existing settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return nil, err
	}

	// Apply updates
	settings.Apply(update)

	// Save the updated settings
	if err := s.settingsRepo.Update(ctx, settings); err != nil {
		return nil, fmt.Errorf("failed to update user settings: %w", err)
	}

	log.Info().
		Int64("user_id", userID).
		Int64("setting_id", settings.ID).
		Str("category", constants.LogCategoryUser).
		Str("event", constants.LogEventUserUpdate).
		Msg("User settings updated")

	return settings, nil
}

// GetBanList retrieves the ban list for a user
func (s *SettingsService) GetBanList(ctx context.Context, userID int64) (*models.BanListWithWords, error) {
	// Get user settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return nil, err
	}

	// Get ban list
	banList, err := s.banListRepo.GetBySettingID(ctx, settings.ID)
	if err != nil {
		if utils.IsNotFoundError(err) {
			// Create a new ban list if one doesn't exist
			banList, err = s.banListRepo.CreateBanList(ctx, settings.ID)
			if err != nil {
				return nil, fmt.Errorf("failed to create ban list: %w", err)
			}
		} else {
			return nil, fmt.Errorf("failed to get ban list: %w", err)
		}
	}

	// Get ban list words
	words, err := s.banListRepo.GetBanListWords(ctx, banList.ID)
	if err != nil {
		return nil, fmt.Errorf("failed to get ban list words: %w", err)
	}

	// Convert to response format
	result := &models.BanListWithWords{
		ID:    banList.ID,
		Words: words,
	}

	return result, nil
}

// AddBanListWords adds words to a user's ban list
func (s *SettingsService) AddBanListWords(ctx context.Context, userID int64, words []string) error {
	// Get user settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return err
	}

	// Get or create ban list
	banList, err := s.banListRepo.GetBySettingID(ctx, settings.ID)
	if err != nil {
		if utils.IsNotFoundError(err) {
			// Create a new ban list if one doesn't exist
			banList, err = s.banListRepo.CreateBanList(ctx, settings.ID)
			if err != nil {
				return fmt.Errorf("failed to create ban list: %w", err)
			}
		} else {
			return fmt.Errorf("failed to get ban list: %w", err)
		}
	}

	// Add words to the ban list
	if err := s.banListRepo.AddWords(ctx, banList.ID, words); err != nil {
		return fmt.Errorf("failed to add words to ban list: %w", err)
	}

	log.Info().
		Int64("user_id", userID).
		Int64("ban_list_id", banList.ID).
		Int("word_count", len(words)).
		Msg("Words added to ban list")

	return nil
}

// RemoveBanListWords removes words from a user's ban list
func (s *SettingsService) RemoveBanListWords(ctx context.Context, userID int64, words []string) error {
	// Get user settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return err
	}

	// Get ban list
	banList, err := s.banListRepo.GetBySettingID(ctx, settings.ID)
	if err != nil {
		if utils.IsNotFoundError(err) {
			// Nothing to remove if ban list doesn't exist
			return nil
		}
		return fmt.Errorf("failed to get ban list: %w", err)
	}

	// Remove words from the ban list
	if err := s.banListRepo.RemoveWords(ctx, banList.ID, words); err != nil {
		return fmt.Errorf("failed to remove words from ban list: %w", err)
	}

	log.Info().
		Int64("user_id", userID).
		Int64("ban_list_id", banList.ID).
		Int("word_count", len(words)).
		Msg("Words removed from ban list")

	return nil
}

// GetSearchPatterns retrieves search patterns for a user
func (s *SettingsService) GetSearchPatterns(ctx context.Context, userID int64) ([]*models.SearchPattern, error) {
	// Get user settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return nil, err
	}

	// Get patterns
	patterns, err := s.patternRepo.GetBySettingID(ctx, settings.ID)
	if err != nil {
		return nil, fmt.Errorf("failed to get search patterns: %w", err)
	}

	return patterns, nil
}

// CreateSearchPattern creates a new search pattern
func (s *SettingsService) CreateSearchPattern(ctx context.Context, userID int64, pattern *models.SearchPatternCreate) (*models.SearchPattern, error) {
	// Get user settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return nil, err
	}

	// Validate pattern type
	patternType := models.PatternType(pattern.PatternType)
	if !models.ValidatePatternType(patternType) {
		return nil, utils.NewValidationError("pattern_type", "Invalid pattern type")
	}

	// Create the search pattern
	newPattern := models.NewSearchPattern(settings.ID, patternType, pattern.PatternText)
	if err := s.patternRepo.Create(ctx, newPattern); err != nil {
		return nil, fmt.Errorf("failed to create search pattern: %w", err)
	}

	log.Info().
		Int64("user_id", userID).
		Int64("pattern_id", newPattern.ID).
		Str("pattern_type", string(newPattern.PatternType)).
		Msg("Search pattern created")

	return newPattern, nil
}

// UpdateSearchPattern updates an existing search pattern
func (s *SettingsService) UpdateSearchPattern(ctx context.Context, userID int64, patternID int64, update *models.SearchPatternUpdate) (*models.SearchPattern, error) {
	// Get user settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return nil, err
	}

	// Get the existing pattern
	pattern, err := s.patternRepo.GetByID(ctx, patternID)
	if err != nil {
		return nil, err
	}

	// Verify that the pattern belongs to the user
	if pattern.SettingID != settings.ID {
		return nil, utils.NewForbiddenError(constants.MsgAccessDenied)
	}

	// Apply updates
	if update.PatternType != "" {
		patternType := models.PatternType(update.PatternType)
		if !models.ValidatePatternType(patternType) {
			return nil, utils.NewValidationError("pattern_type", "Invalid pattern type")
		}
		pattern.PatternType = patternType
	}

	if update.PatternText != "" {
		pattern.PatternText = update.PatternText
	}

	// Save the updated pattern
	if err := s.patternRepo.Update(ctx, pattern); err != nil {
		return nil, fmt.Errorf("failed to update search pattern: %w", err)
	}

	log.Info().
		Int64("user_id", userID).
		Int64("pattern_id", pattern.ID).
		Msg("Search pattern updated")

	return pattern, nil
}

// DeleteSearchPattern removes a search pattern
func (s *SettingsService) DeleteSearchPattern(ctx context.Context, userID int64, patternID int64) error {
	// Get user settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return err
	}

	// Get the pattern to verify ownership
	pattern, err := s.patternRepo.GetByID(ctx, patternID)
	if err != nil {
		return err
	}

	// Verify that the pattern belongs to the user
	if pattern.SettingID != settings.ID {
		return utils.NewForbiddenError(constants.MsgAccessDenied)
	}

	// Delete the pattern
	if err := s.patternRepo.Delete(ctx, patternID); err != nil {
		return fmt.Errorf("failed to delete search pattern: %w", err)
	}

	log.Info().
		Int64("user_id", userID).
		Int64("pattern_id", patternID).
		Msg("Search pattern deleted")

	return nil
}

// GetModelEntities retrieves model entities for a specific method
func (s *SettingsService) GetModelEntities(ctx context.Context, userID int64, methodID int64) ([]*models.ModelEntityWithMethod, error) {
	// Get user settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return nil, err
	}

	// Get model entities
	entities, err := s.modelEntityRepo.GetBySettingIDAndMethodID(ctx, settings.ID, methodID)
	if err != nil {
		return nil, fmt.Errorf("failed to get model entities: %w", err)
	}

	return entities, nil
}

// AddModelEntities adds entities for a specific detection method
func (s *SettingsService) AddModelEntities(ctx context.Context, userID int64, batch *models.ModelEntityBatch) ([]*models.ModelEntity, error) {
	// Get user settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return nil, err
	}

	// Create model entities
	var entities []*models.ModelEntity
	for _, text := range batch.EntityTexts {
		entity := models.NewModelEntity(settings.ID, batch.MethodID, text)
		entities = append(entities, entity)
	}

	// Add the entities
	if err := s.modelEntityRepo.CreateBatch(ctx, entities); err != nil {
		return nil, fmt.Errorf("failed to create model entities: %w", err)
	}

	log.Info().
		Int64("user_id", userID).
		Int64("method_id", batch.MethodID).
		Int("entity_count", len(entities)).
		Msg("Model entities added")

	return entities, nil
}

// DeleteModelEntity removes a model entity
func (s *SettingsService) DeleteModelEntity(ctx context.Context, userID int64, entityID int64) error {
	// Get user settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return err
	}

	// Get the entity to verify ownership
	entity, err := s.modelEntityRepo.GetByID(ctx, entityID)
	if err != nil {
		return err
	}

	// Verify that the entity belongs to the user
	if entity.SettingID != settings.ID {
		return utils.NewForbiddenError(constants.MsgAccessDenied)
	}

	// Delete the entity
	if err := s.modelEntityRepo.Delete(ctx, entityID); err != nil {
		return fmt.Errorf("failed to delete model entity: %w", err)
	}

	log.Info().
		Int64("user_id", userID).
		Int64("entity_id", entityID).
		Msg("Model entity deleted")

	return nil
}

// DeleteModelEntityByMethodID removes model entities for a specific method
func (s *SettingsService) DeleteModelEntityByMethodID(ctx context.Context, userID int64, methodID int64) error {
	// Get user settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return err
	}

	// Delete the model entities by method ID
	if err := s.modelEntityRepo.DeleteByMethodID(ctx, settings.ID, methodID); err != nil {
		return fmt.Errorf("failed to delete model entities by method ID: %w", err)
	}

	log.Info().
		Int64("user_id", userID).
		Int64("method_id", methodID).
		Msg("Model entities deleted by method ID")

	return nil
}

// ExportSettings exports all settings for a user
func (s *SettingsService) ExportSettings(ctx context.Context, userID int64) (*models.SettingsExport, error) {
	// Get user settings
	settings, err := s.GetUserSettings(ctx, userID)
	if err != nil {
		return nil, err
	}

	// Get ban list
	banList, err := s.GetBanList(ctx, userID)
	if err != nil {
		return nil, err
	}

	// Get search patterns
	patterns, err := s.GetSearchPatterns(ctx, userID)
	if err != nil {
		return nil, err
	}

	// Get all model entities grouped by method
	var allEntities []*models.ModelEntityWithMethod

	// First, get unique method IDs from settings
	methodIDs := make(map[int64]bool)
	settingID := settings.ID

	// Get entities for the user's settings
	entities, err := s.modelEntityRepo.GetBySettingID(ctx, settingID)
	if err != nil {
		return nil, fmt.Errorf("failed to get model entities: %w", err)
	}

	// Get unique method IDs
	for _, entity := range entities {
		methodIDs[entity.MethodID] = true
	}

	// Fetch detailed entities with method info for each method
	for methodID := range methodIDs {
		entitiesWithMethod, err := s.modelEntityRepo.GetBySettingIDAndMethodID(ctx, settingID, methodID)
		if err != nil {
			return nil, fmt.Errorf("failed to get entities for method %d: %w", methodID, err)
		}
		allEntities = append(allEntities, entitiesWithMethod...)
	}

	// Build export object
	export := &models.SettingsExport{
		UserID:          userID,
		ExportDate:      time.Now(),
		GeneralSettings: settings,
		BanList:         banList,
		SearchPatterns:  patterns,
		ModelEntities:   allEntities,
	}

	return export, nil
}

// ImportSettings imports settings for a user
func (s *SettingsService) ImportSettings(ctx context.Context, userID int64, importData *models.SettingsExport) error {
	// 1. Update general settings
	// Create an update object based on the imported settings
	update := &models.UserSettingsUpdate{
		RemoveImages:           &importData.GeneralSettings.RemoveImages,
		Theme:                  &importData.GeneralSettings.Theme,
		AutoProcessing:         &importData.GeneralSettings.AutoProcessing,
		DetectionThreshold:     &importData.GeneralSettings.DetectionThreshold,
		UseBanlistForDetection: &importData.GeneralSettings.UseBanlistForDetection,
	}

	// Use _ to discard the first return value since we only need the error
	_, err := s.UpdateUserSettings(ctx, userID, update)
	if err != nil {
		return fmt.Errorf("failed to update general settings: %w", err)
	}

	// 2. Handle ban list words - first get current words to remove them
	currentBanList, err := s.GetBanList(ctx, userID)
	if err != nil {
		return fmt.Errorf("failed to get current ban list: %w", err)
	}

	// Remove existing words
	if len(currentBanList.Words) > 0 {
		if err := s.RemoveBanListWords(ctx, userID, currentBanList.Words); err != nil {
			return fmt.Errorf("failed to clear ban list: %w", err)
		}
	}

	// Add new words
	if len(importData.BanList.Words) > 0 {
		if err := s.AddBanListWords(ctx, userID, importData.BanList.Words); err != nil {
			return fmt.Errorf("failed to import ban list words: %w", err)
		}
	}

	// 3. Handle search patterns
	// Delete existing patterns
	existingPatterns, err := s.GetSearchPatterns(ctx, userID)
	if err != nil {
		return fmt.Errorf("failed to get existing search patterns: %w", err)
	}

	for _, pattern := range existingPatterns {
		if err := s.DeleteSearchPattern(ctx, userID, pattern.ID); err != nil {
			return fmt.Errorf("failed to delete existing pattern: %w", err)
		}
	}

	// Create new patterns
	for _, pattern := range importData.SearchPatterns {
		// Create a pattern create object from the pattern
		createPattern := &models.SearchPatternCreate{
			PatternType: string(pattern.PatternType),
			PatternText: pattern.PatternText,
		}

		_, err := s.CreateSearchPattern(ctx, userID, createPattern)
		if err != nil {
			return fmt.Errorf("failed to create search pattern: %w", err)
		}
	}

	// 4. Handle model entities
	// Group entities by method ID
	methodEntities := make(map[int64][]string)
	for _, entity := range importData.ModelEntities {
		methodEntities[entity.MethodID] = append(methodEntities[entity.MethodID], entity.EntityText)
	}

	// For each method, delete existing entities and create new ones
	for methodID, entities := range methodEntities {
		// Delete existing entities for this method
		if err := s.DeleteModelEntityByMethodID(ctx, userID, methodID); err != nil {
			return fmt.Errorf("failed to delete existing entities for method %d: %w", methodID, err)
		}

		// Create new entities if there are any
		if len(entities) > 0 {
			batch := &models.ModelEntityBatch{
				MethodID:    methodID,
				EntityTexts: entities,
			}

			_, err := s.AddModelEntities(ctx, userID, batch)
			if err != nil {
				return fmt.Errorf("failed to add model entities for method %d: %w", methodID, err)
			}
		}
	}

	return nil
}
