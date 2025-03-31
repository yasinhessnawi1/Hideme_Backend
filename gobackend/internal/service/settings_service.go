package service

import (
	"context"
	"fmt"

	"github.com/rs/zerolog/log"

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
		return nil, utils.NewForbiddenError("You do not have permission to update this pattern")
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
		return utils.NewForbiddenError("You do not have permission to delete this pattern")
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
		return utils.NewForbiddenError("You do not have permission to delete this entity")
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
