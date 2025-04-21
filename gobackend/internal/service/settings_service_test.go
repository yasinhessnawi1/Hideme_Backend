package service

import (
	"context"
	"fmt"
	"testing"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// Mock implementations for testing
type MockSettingsRepository struct {
	settings     map[int64]*models.UserSetting
	nextID       int64
	validUserIDs map[int64]bool // Added to track valid user IDs
}

func NewMockSettingsRepository() *MockSettingsRepository {
	return &MockSettingsRepository{
		settings:     make(map[int64]*models.UserSetting),
		nextID:       1,
		validUserIDs: make(map[int64]bool),
	}
}

// RegisterValidUserID registers a user ID as valid
func (m *MockSettingsRepository) RegisterValidUserID(userID int64) {
	m.validUserIDs[userID] = true
}

func (m *MockSettingsRepository) Create(ctx context.Context, settings *models.UserSetting) error {
	settings.ID = m.nextID
	m.nextID++

	m.settings[settings.UserID] = settings

	return nil
}

func (m *MockSettingsRepository) GetByUserID(ctx context.Context, userID int64) (*models.UserSetting, error) {
	settings, ok := m.settings[userID]
	if !ok {
		return nil, utils.NewNotFoundError("UserSetting", userID)
	}
	return settings, nil
}

func (m *MockSettingsRepository) Update(ctx context.Context, settings *models.UserSetting) error {
	if _, ok := m.settings[settings.UserID]; !ok {
		return utils.NewNotFoundError("UserSetting", settings.UserID)
	}

	m.settings[settings.UserID] = settings

	return nil
}

func (m *MockSettingsRepository) Delete(ctx context.Context, id int64) error {
	for userID, settings := range m.settings {
		if settings.ID == id {
			delete(m.settings, userID)
			return nil
		}
	}

	return utils.NewNotFoundError("UserSetting", id)
}

func (m *MockSettingsRepository) DeleteByUserID(ctx context.Context, userID int64) error {
	if _, ok := m.settings[userID]; !ok {
		return utils.NewNotFoundError("UserSetting", userID)
	}

	delete(m.settings, userID)

	return nil
}

func (m *MockSettingsRepository) EnsureDefaultSettings(ctx context.Context, userID int64) (*models.UserSetting, error) {
	// Check if user ID is valid
	if !m.validUserIDs[userID] {
		return nil, utils.NewNotFoundError("User", userID)
	}

	settings, ok := m.settings[userID]
	if !ok {
		settings = models.NewUserSetting(userID)
		err := m.Create(ctx, settings)
		if err != nil {
			return nil, err
		}
	}

	return settings, nil
}

type MockBanListRepository struct {
	banLists    map[int64]*models.BanList
	banListsMap map[int64]int64 // settingID -> banListID
	words       map[int64]map[string]bool
	nextID      int64
}

func NewMockBanListRepository() *MockBanListRepository {
	return &MockBanListRepository{
		banLists:    make(map[int64]*models.BanList),
		banListsMap: make(map[int64]int64),
		words:       make(map[int64]map[string]bool),
		nextID:      1,
	}
}

func (m *MockBanListRepository) GetByID(ctx context.Context, id int64) (*models.BanList, error) {
	banList, ok := m.banLists[id]
	if !ok {
		return nil, utils.NewNotFoundError("BanList", id)
	}
	return banList, nil
}

func (m *MockBanListRepository) GetBySettingID(ctx context.Context, settingID int64) (*models.BanList, error) {
	banListID, ok := m.banListsMap[settingID]
	if !ok {
		return nil, utils.NewNotFoundError("BanList", settingID)
	}

	return m.banLists[banListID], nil
}

func (m *MockBanListRepository) CreateBanList(ctx context.Context, settingID int64) (*models.BanList, error) {
	if _, ok := m.banListsMap[settingID]; ok {
		return nil, utils.NewDuplicateError("BanList", "setting_id", settingID)
	}

	banList := &models.BanList{
		ID:        m.nextID,
		SettingID: settingID,
	}
	m.nextID++

	m.banLists[banList.ID] = banList
	m.banListsMap[settingID] = banList.ID
	m.words[banList.ID] = make(map[string]bool)

	return banList, nil
}

func (m *MockBanListRepository) Delete(ctx context.Context, id int64) error {
	banList, ok := m.banLists[id]
	if !ok {
		return utils.NewNotFoundError("BanList", id)
	}

	delete(m.banListsMap, banList.SettingID)
	delete(m.banLists, id)
	delete(m.words, id)

	return nil
}

func (m *MockBanListRepository) GetBanListWords(ctx context.Context, banListID int64) ([]string, error) {
	wordMap, ok := m.words[banListID]
	if !ok {
		return nil, utils.NewNotFoundError("BanList", banListID)
	}

	var words []string
	for word := range wordMap {
		words = append(words, word)
	}

	return words, nil
}

func (m *MockBanListRepository) AddWords(ctx context.Context, banListID int64, words []string) error {
	wordMap, ok := m.words[banListID]
	if !ok {
		return utils.NewNotFoundError("BanList", banListID)
	}

	for _, word := range words {
		wordMap[word] = true
	}

	return nil
}

func (m *MockBanListRepository) RemoveWords(ctx context.Context, banListID int64, words []string) error {
	wordMap, ok := m.words[banListID]
	if !ok {
		return utils.NewNotFoundError("BanList", banListID)
	}

	for _, word := range words {
		delete(wordMap, word)
	}

	return nil
}

func (m *MockBanListRepository) WordExists(ctx context.Context, banListID int64, word string) (bool, error) {
	wordMap, ok := m.words[banListID]
	if !ok {
		return false, utils.NewNotFoundError("BanList", banListID)
	}

	return wordMap[word], nil
}

type MockPatternRepository struct {
	patterns     map[int64]*models.SearchPattern
	patternsByID map[int64][]*models.SearchPattern
	nextID       int64
}

func NewMockPatternRepository() *MockPatternRepository {
	return &MockPatternRepository{
		patterns:     make(map[int64]*models.SearchPattern),
		patternsByID: make(map[int64][]*models.SearchPattern),
		nextID:       1,
	}
}

func (m *MockPatternRepository) Create(ctx context.Context, pattern *models.SearchPattern) error {
	pattern.ID = m.nextID
	m.nextID++

	m.patterns[pattern.ID] = pattern
	m.patternsByID[pattern.SettingID] = append(m.patternsByID[pattern.SettingID], pattern)

	return nil
}

func (m *MockPatternRepository) GetByID(ctx context.Context, id int64) (*models.SearchPattern, error) {
	pattern, ok := m.patterns[id]
	if !ok {
		return nil, utils.NewNotFoundError("SearchPattern", id)
	}
	return pattern, nil
}

func (m *MockPatternRepository) GetBySettingID(ctx context.Context, settingID int64) ([]*models.SearchPattern, error) {
	return m.patternsByID[settingID], nil
}

func (m *MockPatternRepository) Update(ctx context.Context, pattern *models.SearchPattern) error {
	if _, ok := m.patterns[pattern.ID]; !ok {
		return utils.NewNotFoundError("SearchPattern", pattern.ID)
	}

	m.patterns[pattern.ID] = pattern

	// Update in the setting patterns list
	var patterns []*models.SearchPattern
	for _, p := range m.patternsByID[pattern.SettingID] {
		if p.ID == pattern.ID {
			patterns = append(patterns, pattern)
		} else {
			patterns = append(patterns, p)
		}
	}

	m.patternsByID[pattern.SettingID] = patterns

	return nil
}

func (m *MockPatternRepository) Delete(ctx context.Context, id int64) error {
	pattern, ok := m.patterns[id]
	if !ok {
		return utils.NewNotFoundError("SearchPattern", id)
	}

	delete(m.patterns, id)

	// Remove from the setting patterns list
	var patterns []*models.SearchPattern
	for _, p := range m.patternsByID[pattern.SettingID] {
		if p.ID != id {
			patterns = append(patterns, p)
		}
	}

	m.patternsByID[pattern.SettingID] = patterns

	return nil
}

func (m *MockPatternRepository) DeleteBySettingID(ctx context.Context, settingID int64) error {
	patterns := m.patternsByID[settingID]

	for _, pattern := range patterns {
		delete(m.patterns, pattern.ID)
	}

	delete(m.patternsByID, settingID)

	return nil
}

type MockModelEntityRepository struct {
	entities     map[int64]*models.ModelEntity
	entitiesByID map[int64][]*models.ModelEntity
	nextID       int64
}

func NewMockModelEntityRepository() *MockModelEntityRepository {
	return &MockModelEntityRepository{
		entities:     make(map[int64]*models.ModelEntity),
		entitiesByID: make(map[int64][]*models.ModelEntity),
		nextID:       1,
	}
}

func (m *MockModelEntityRepository) Create(ctx context.Context, entity *models.ModelEntity) error {
	entity.ID = m.nextID
	m.nextID++

	m.entities[entity.ID] = entity
	m.entitiesByID[entity.SettingID] = append(m.entitiesByID[entity.SettingID], entity)

	return nil
}

func (m *MockModelEntityRepository) CreateBatch(ctx context.Context, entities []*models.ModelEntity) error {
	for _, entity := range entities {
		if err := m.Create(ctx, entity); err != nil {
			return err
		}
	}

	return nil
}

func (m *MockModelEntityRepository) GetByID(ctx context.Context, id int64) (*models.ModelEntity, error) {
	entity, ok := m.entities[id]
	if !ok {
		return nil, utils.NewNotFoundError("ModelEntity", id)
	}
	return entity, nil
}

func (m *MockModelEntityRepository) GetBySettingID(ctx context.Context, settingID int64) ([]*models.ModelEntity, error) {
	return m.entitiesByID[settingID], nil
}

func (m *MockModelEntityRepository) GetBySettingIDAndMethodID(ctx context.Context, settingID, methodID int64) ([]*models.ModelEntityWithMethod, error) {
	var entities []*models.ModelEntityWithMethod

	for _, entity := range m.entitiesByID[settingID] {
		if entity.MethodID == methodID {
			entities = append(entities, &models.ModelEntityWithMethod{
				ModelEntity: *entity,
				MethodName:  fmt.Sprintf("Method %d", methodID),
			})
		}
	}

	return entities, nil
}

func (m *MockModelEntityRepository) Update(ctx context.Context, entity *models.ModelEntity) error {
	if _, ok := m.entities[entity.ID]; !ok {
		return utils.NewNotFoundError("ModelEntity", entity.ID)
	}

	m.entities[entity.ID] = entity

	// Update in the setting entities list
	var entities []*models.ModelEntity
	for _, e := range m.entitiesByID[entity.SettingID] {
		if e.ID == entity.ID {
			entities = append(entities, entity)
		} else {
			entities = append(entities, e)
		}
	}

	m.entitiesByID[entity.SettingID] = entities

	return nil
}

func (m *MockModelEntityRepository) Delete(ctx context.Context, id int64) error {
	entity, ok := m.entities[id]
	if !ok {
		return utils.NewNotFoundError("ModelEntity", id)
	}

	delete(m.entities, id)

	// Remove from the setting entities list
	var entities []*models.ModelEntity
	for _, e := range m.entitiesByID[entity.SettingID] {
		if e.ID != id {
			entities = append(entities, e)
		}
	}

	m.entitiesByID[entity.SettingID] = entities

	return nil
}

func (m *MockModelEntityRepository) DeleteBySettingID(ctx context.Context, settingID int64) error {
	entities := m.entitiesByID[settingID]

	for _, entity := range entities {
		delete(m.entities, entity.ID)
	}

	delete(m.entitiesByID, settingID)

	return nil
}

func (m *MockModelEntityRepository) DeleteByMethodID(ctx context.Context, settingID, methodID int64) error {
	var remainingEntities []*models.ModelEntity

	for _, entity := range m.entitiesByID[settingID] {
		if entity.MethodID == methodID {
			delete(m.entities, entity.ID)
		} else {
			remainingEntities = append(remainingEntities, entity)
		}
	}

	m.entitiesByID[settingID] = remainingEntities

	return nil
}

func TestNewSettingsService(t *testing.T) {
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	if service == nil {
		t.Error("Expected non-nil service")
	}
}

func TestSettingsService_GetUserSettings(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	// Register valid user ID
	userID := int64(123)
	settingsRepo.RegisterValidUserID(userID)

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Test getting settings for a user without settings
	settings, err := service.GetUserSettings(context.Background(), userID)

	// Check that default settings were created
	if err != nil {
		t.Errorf("GetUserSettings() error = %v", err)
	}

	if settings == nil {
		t.Fatal("Expected non-nil settings")
	}

	if settings.UserID != userID {
		t.Errorf("Expected UserID = %d, got %d", userID, settings.UserID)
	}

	// Check that settings were stored
	storedSettings, err := settingsRepo.GetByUserID(context.Background(), userID)
	if err != nil {
		t.Errorf("Failed to get stored settings: %v", err)
	}

	if storedSettings.ID != settings.ID {
		t.Errorf("Expected ID = %d, got %d", settings.ID, storedSettings.ID)
	}

	// Test getting settings for a user with existing settings
	settings2, err := service.GetUserSettings(context.Background(), userID)

	// Check that we get the same settings
	if err != nil {
		t.Errorf("GetUserSettings() error = %v", err)
	}

	if settings2.ID != settings.ID {
		t.Errorf("Expected ID = %d, got %d", settings.ID, settings2.ID)
	}

	// Test error case - user not found
	_, err = service.GetUserSettings(context.Background(), int64(999))
	if err == nil {
		t.Error("Expected error for non-existent user, got nil")
	}
}

func TestSettingsService_UpdateUserSettings(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	// Register valid user ID
	userID := int64(123)
	settingsRepo.RegisterValidUserID(userID)

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Create initial settings
	initialSettings, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get initial settings: %v", err)
	}

	// Verify initial values
	if initialSettings.RemoveImages != true {
		t.Errorf("Expected default RemoveImages = true, got %v", initialSettings.RemoveImages)
	}

	// Test updating various settings
	tests := []struct {
		name   string
		update *models.UserSettingsUpdate
		check  func(t *testing.T, settings *models.UserSetting)
	}{
		{
			name: "Update RemoveImages",
			update: &models.UserSettingsUpdate{
				RemoveImages: boolPtr(false),
			},
			check: func(t *testing.T, settings *models.UserSetting) {
				if settings.RemoveImages != false {
					t.Errorf("Expected RemoveImages = false, got %v", settings.RemoveImages)
				}
			},
		},
		{
			name: "Update Theme",
			update: &models.UserSettingsUpdate{
				Theme: stringPtr("dark"),
			},
			check: func(t *testing.T, settings *models.UserSetting) {
				if settings.Theme != "dark" {
					t.Errorf("Expected Theme = dark, got %s", settings.Theme)
				}
			},
		},
		{
			name: "Update AutoProcessing",
			update: &models.UserSettingsUpdate{
				AutoProcessing: boolPtr(false),
			},
			check: func(t *testing.T, settings *models.UserSetting) {
				if settings.AutoProcessing != false {
					t.Errorf("Expected AutoProcessing = false, got %v", settings.AutoProcessing)
				}
			},
		},
		{
			name: "Update DetectionThreshold",
			update: &models.UserSettingsUpdate{
				DetectionThreshold: float64Ptr(0.75),
			},
			check: func(t *testing.T, settings *models.UserSetting) {
				if settings.DetectionThreshold != 0.75 {
					t.Errorf("Expected DetectionThreshold = 0.75, got %v", settings.DetectionThreshold)
				}
			},
		},
		{
			name: "Update UseBanlistForDetection",
			update: &models.UserSettingsUpdate{
				UseBanlistForDetection: boolPtr(false),
			},
			check: func(t *testing.T, settings *models.UserSetting) {
				if settings.UseBanlistForDetection != false {
					t.Errorf("Expected UseBanlistForDetection = false, got %v", settings.UseBanlistForDetection)
				}
			},
		},
		{
			name: "Update multiple settings",
			update: &models.UserSettingsUpdate{
				RemoveImages:   boolPtr(true),
				Theme:          stringPtr("system"),
				AutoProcessing: boolPtr(true),
			},
			check: func(t *testing.T, settings *models.UserSetting) {
				if settings.RemoveImages != true {
					t.Errorf("Expected RemoveImages = true, got %v", settings.RemoveImages)
				}
				if settings.Theme != "system" {
					t.Errorf("Expected Theme = system, got %s", settings.Theme)
				}
				if settings.AutoProcessing != true {
					t.Errorf("Expected AutoProcessing = true, got %v", settings.AutoProcessing)
				}
			},
		},
	}

	// Run tests
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			updatedSettings, err := service.UpdateUserSettings(context.Background(), userID, tc.update)
			if err != nil {
				t.Fatalf("UpdateUserSettings() error = %v", err)
			}

			if updatedSettings == nil {
				t.Fatal("Expected non-nil settings")
			}

			// Check that the updates were applied
			tc.check(t, updatedSettings)

			// Verify that the settings were persisted
			storedSettings, err := settingsRepo.GetByUserID(context.Background(), userID)
			if err != nil {
				t.Errorf("Failed to get stored settings: %v", err)
			}

			// Run the same checks on the stored settings
			tc.check(t, storedSettings)
		})
	}

	// Test error case - user not found
	_, err = service.UpdateUserSettings(context.Background(), int64(999), &models.UserSettingsUpdate{
		RemoveImages: boolPtr(false),
	})
	if err == nil {
		t.Error("Expected error for non-existent user, got nil")
	}
}

func TestSettingsService_GetBanList(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	// Register valid user IDs
	userID := int64(123)
	newUserID := int64(456)
	settingsRepo.RegisterValidUserID(userID)
	settingsRepo.RegisterValidUserID(newUserID)

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	settings, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Create a ban list
	banList, err := banListRepo.CreateBanList(context.Background(), settings.ID)
	if err != nil {
		t.Fatalf("Failed to create ban list: %v", err)
	}

	// Add some words
	err = banListRepo.AddWords(context.Background(), banList.ID, []string{"word1", "word2"})
	if err != nil {
		t.Fatalf("Failed to add words: %v", err)
	}

	// Get ban list
	banListWithWords, err := service.GetBanList(context.Background(), userID)

	// Check results
	if err != nil {
		t.Errorf("GetBanList() error = %v", err)
	}

	if banListWithWords == nil {
		t.Fatal("Expected non-nil ban list")
	}

	if banListWithWords.ID != banList.ID {
		t.Errorf("Expected ID = %d, got %d", banList.ID, banListWithWords.ID)
	}

	if len(banListWithWords.Words) != 2 {
		t.Errorf("Expected 2 words, got %d", len(banListWithWords.Words))
	}

	// Test getting ban list for a user without a ban list
	_, err = service.GetUserSettings(context.Background(), newUserID)
	if err != nil {
		t.Fatalf("Failed to get new user settings: %v", err)
	}

	banListWithWords, err = service.GetBanList(context.Background(), newUserID)

	// Check that a new ban list was created
	if err != nil {
		t.Errorf("GetBanList() error = %v", err)
	}

	if banListWithWords == nil {
		t.Fatal("Expected non-nil ban list")
	}

	if len(banListWithWords.Words) != 0 {
		t.Errorf("Expected 0 words, got %d", len(banListWithWords.Words))
	}

	// Test error case - user not found
	_, err = service.GetBanList(context.Background(), int64(999))
	if err == nil {
		t.Error("Expected error for non-existent user, got nil")
	}
}

func TestSettingsService_AddBanListWords(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	// Register valid user ID
	userID := int64(123)
	settingsRepo.RegisterValidUserID(userID)

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	_, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Test adding words to a new ban list
	words := []string{"sensitive", "confidential", "restricted"}
	err = service.AddBanListWords(context.Background(), userID, words)
	if err != nil {
		t.Fatalf("AddBanListWords() error = %v", err)
	}

	// Get the ban list to verify words were added
	banList, err := service.GetBanList(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get ban list: %v", err)
	}

	if len(banList.Words) != 3 {
		t.Errorf("Expected 3 words, got %d", len(banList.Words))
	}

	// Check if all words are present
	wordMap := make(map[string]bool)
	for _, word := range banList.Words {
		wordMap[word] = true
	}

	for _, word := range words {
		if !wordMap[word] {
			t.Errorf("Expected word '%s' to be in ban list", word)
		}
	}

	// Test adding more words
	moreWords := []string{"classified", "private"}
	err = service.AddBanListWords(context.Background(), userID, moreWords)
	if err != nil {
		t.Fatalf("AddBanListWords() error = %v", err)
	}

	// Get the ban list again to verify all words
	banList, err = service.GetBanList(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get ban list: %v", err)
	}

	if len(banList.Words) != 5 {
		t.Errorf("Expected 5 words, got %d", len(banList.Words))
	}

	// Check if all words are present
	wordMap = make(map[string]bool)
	for _, word := range banList.Words {
		wordMap[word] = true
	}

	allWords := append(words, moreWords...)
	for _, word := range allWords {
		if !wordMap[word] {
			t.Errorf("Expected word '%s' to be in ban list", word)
		}
	}

	// Test error case - user not found
	err = service.AddBanListWords(context.Background(), int64(999), []string{"test"})
	if err == nil {
		t.Error("Expected error for non-existent user, got nil")
	}
}

func TestSettingsService_RemoveBanListWords(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	// Register valid user IDs
	userID := int64(123)
	newUserID := int64(456)
	settingsRepo.RegisterValidUserID(userID)
	settingsRepo.RegisterValidUserID(newUserID)

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	settings, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Create a ban list with words
	banList, err := banListRepo.CreateBanList(context.Background(), settings.ID)
	if err != nil {
		t.Fatalf("Failed to create ban list: %v", err)
	}

	initialWords := []string{"sensitive", "confidential", "restricted", "classified", "private"}
	err = banListRepo.AddWords(context.Background(), banList.ID, initialWords)
	if err != nil {
		t.Fatalf("Failed to add words: %v", err)
	}

	// Test removing some words
	wordsToRemove := []string{"sensitive", "confidential"}
	err = service.RemoveBanListWords(context.Background(), userID, wordsToRemove)
	if err != nil {
		t.Fatalf("RemoveBanListWords() error = %v", err)
	}

	// Get the ban list to verify words were removed
	banListWithWords, err := service.GetBanList(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get ban list: %v", err)
	}

	if len(banListWithWords.Words) != 3 {
		t.Errorf("Expected 3 words, got %d", len(banListWithWords.Words))
	}

	// Check that removed words are no longer present
	wordMap := make(map[string]bool)
	for _, word := range banListWithWords.Words {
		wordMap[word] = true
	}

	for _, word := range wordsToRemove {
		if wordMap[word] {
			t.Errorf("Word '%s' should have been removed from ban list", word)
		}
	}

	// Test removing words that don't exist
	nonExistentWords := []string{"nonexistent", "missing"}
	err = service.RemoveBanListWords(context.Background(), userID, nonExistentWords)
	if err != nil {
		t.Fatalf("RemoveBanListWords() error = %v", err)
	}

	// Verify count is still 3
	banListWithWords, err = service.GetBanList(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get ban list: %v", err)
	}

	if len(banListWithWords.Words) != 3 {
		t.Errorf("Expected 3 words, got %d", len(banListWithWords.Words))
	}

	// Test removing all remaining words
	remainingWords := []string{"restricted", "classified", "private"}
	err = service.RemoveBanListWords(context.Background(), userID, remainingWords)
	if err != nil {
		t.Fatalf("RemoveBanListWords() error = %v", err)
	}

	// Verify count is now 0
	banListWithWords, err = service.GetBanList(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get ban list: %v", err)
	}

	if len(banListWithWords.Words) != 0 {
		t.Errorf("Expected 0 words, got %d", len(banListWithWords.Words))
	}

	// Test error case - user not found
	err = service.RemoveBanListWords(context.Background(), int64(999), []string{"test"})
	if err == nil {
		t.Error("Expected error for non-existent user, got nil")
	}

	// Test for non-existent ban list (e.g., if the ban list was deleted)
	_, err = service.GetUserSettings(context.Background(), newUserID)
	if err != nil {
		t.Fatalf("Failed to get new user settings: %v", err)
	}

	// Remove a word from a non-existent ban list (will be no-op)
	err = service.RemoveBanListWords(context.Background(), newUserID, []string{"test"})
	if err != nil {
		t.Errorf("RemoveBanListWords() error = %v", err)
	}
}

func TestSettingsService_GetSearchPatterns(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	// Register valid user IDs
	userID := int64(123)
	newUserID := int64(456)
	settingsRepo.RegisterValidUserID(userID)
	settingsRepo.RegisterValidUserID(newUserID)

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	settings, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Create some search patterns
	pattern1 := models.NewSearchPattern(settings.ID, models.CaseSensitive, `\b\d{3}-\d{2}-\d{4}\b`)
	err = patternRepo.Create(context.Background(), pattern1)
	if err != nil {
		t.Fatalf("Failed to create pattern: %v", err)
	}

	pattern2 := models.NewSearchPattern(settings.ID, models.Normal, "confidential document")
	err = patternRepo.Create(context.Background(), pattern2)
	if err != nil {
		t.Fatalf("Failed to create pattern: %v", err)
	}

	// Test getting all patterns
	patterns, err := service.GetSearchPatterns(context.Background(), userID)
	if err != nil {
		t.Fatalf("GetSearchPatterns() error = %v", err)
	}

	if len(patterns) != 2 {
		t.Errorf("Expected 2 patterns, got %d", len(patterns))
	}

	// Verify pattern details
	patternMap := make(map[int64]*models.SearchPattern)
	for _, p := range patterns {
		patternMap[p.ID] = p
	}

	p1 := patternMap[pattern1.ID]
	if p1 == nil {
		t.Fatalf("Pattern 1 not found in results")
	}
	if p1.PatternType != models.CaseSensitive {
		t.Errorf("Expected PatternType = %s, got %s", models.CaseSensitive, p1.PatternType)
	}
	if p1.PatternText != `\b\d{3}-\d{2}-\d{4}\b` {
		t.Errorf("Expected PatternText = '\\b\\d{3}-\\d{2}-\\d{4}\\b', got %s", p1.PatternText)
	}

	p2 := patternMap[pattern2.ID]
	if p2 == nil {
		t.Fatalf("Pattern 2 not found in results")
	}
	if p2.PatternType != models.Normal {
		t.Errorf("Expected PatternType = %s, got %s", models.Normal, p2.PatternType)
	}
	if p2.PatternText != "confidential document" {
		t.Errorf("Expected PatternText = 'confidential document', got %s", p2.PatternText)
	}

	// Test getting patterns for a user with no patterns
	_, err = service.GetUserSettings(context.Background(), newUserID)
	if err != nil {
		t.Fatalf("Failed to get new user settings: %v", err)
	}

	patterns, err = service.GetSearchPatterns(context.Background(), newUserID)
	if err != nil {
		t.Fatalf("GetSearchPatterns() error = %v", err)
	}

	if len(patterns) != 0 {
		t.Errorf("Expected 0 patterns, got %d", len(patterns))
	}

	// Test error case - user not found
	_, err = service.GetSearchPatterns(context.Background(), int64(999))
	if err == nil {
		t.Error("Expected error for non-existent user, got nil")
	}
}

func TestSettingsService_CreateSearchPattern(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	// Register valid user ID
	userID := int64(123)
	settingsRepo.RegisterValidUserID(userID)

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	_, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Test cases
	tests := []struct {
		name        string
		patternType string
		patternText string
		expectError bool
	}{
		{
			name:        "Valid Regex pattern",
			patternType: string(models.CaseSensitive),
			patternText: `\b\d{3}-\d{2}-\d{4}\b`,
			expectError: false,
		},
		{
			name:        "Valid Normal pattern",
			patternType: string(models.Normal),
			patternText: "confidential document",
			expectError: false,
		},
		{
			name:        "Invalid pattern type",
			patternType: "InvalidType",
			patternText: "test pattern",
			expectError: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			pattern := &models.SearchPatternCreate{
				PatternType: tc.patternType,
				PatternText: tc.patternText,
			}

			createdPattern, err := service.CreateSearchPattern(context.Background(), userID, pattern)

			if tc.expectError {
				if err == nil {
					t.Error("Expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Fatalf("CreateSearchPattern() error = %v", err)
			}

			if createdPattern == nil {
				t.Fatal("Expected non-nil pattern")
			}

			if string(createdPattern.PatternType) != tc.patternType {
				t.Errorf("Expected PatternType = %s, got %s", tc.patternType, createdPattern.PatternType)
			}

			if createdPattern.PatternText != tc.patternText {
				t.Errorf("Expected PatternText = %s, got %s", tc.patternText, createdPattern.PatternText)
			}

			// Verify the pattern was stored
			patterns, err := service.GetSearchPatterns(context.Background(), userID)
			if err != nil {
				t.Fatalf("Failed to get patterns: %v", err)
			}

			found := false
			for _, p := range patterns {
				if p.ID == createdPattern.ID {
					found = true
					break
				}
			}

			if !found {
				t.Error("Created pattern not found in stored patterns")
			}
		})
	}

	// Test error case - user not found
	_, err = service.CreateSearchPattern(context.Background(), int64(999), &models.SearchPatternCreate{
		PatternType: string(models.CaseSensitive),
		PatternText: "test",
	})
	if err == nil {
		t.Error("Expected error for non-existent user, got nil")
	}
}

func TestSettingsService_UpdateSearchPattern(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	// Register valid user IDs
	userID := int64(123)
	newUserID := int64(456)
	settingsRepo.RegisterValidUserID(userID)
	settingsRepo.RegisterValidUserID(newUserID)

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	settings, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Create a pattern to update
	pattern := models.NewSearchPattern(settings.ID, models.CaseSensitive, `\b\d{3}-\d{2}-\d{4}\b`)
	err = patternRepo.Create(context.Background(), pattern)
	if err != nil {
		t.Fatalf("Failed to create pattern: %v", err)
	}

	// Test cases
	tests := []struct {
		name        string
		update      *models.SearchPatternUpdate
		expectError bool
		check       func(t *testing.T, pattern *models.SearchPattern)
	}{
		{
			name: "Update pattern text only",
			update: &models.SearchPatternUpdate{
				PatternText: `\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b`,
			},
			expectError: false,
			check: func(t *testing.T, pattern *models.SearchPattern) {
				if pattern.PatternText != `\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b` {
					t.Errorf("Expected PatternText = '\\b\\d{3}-\\d{2}-\\d{4}\\b|\\b\\d{9}\\b', got %s", pattern.PatternText)
				}
				if pattern.PatternType != models.CaseSensitive {
					t.Errorf("Expected PatternType to remain %s, got %s", models.CaseSensitive, pattern.PatternType)
				}
			},
		},
		{
			name: "Update pattern type only",
			update: &models.SearchPatternUpdate{
				PatternType: string(models.Normal),
			},
			expectError: false,
			check: func(t *testing.T, pattern *models.SearchPattern) {
				if pattern.PatternType != models.Normal {
					t.Errorf("Expected PatternType = %s, got %s", models.Normal, pattern.PatternType)
				}
				if pattern.PatternText != `\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b` {
					t.Errorf("Expected PatternText to remain '\\b\\d{3}-\\d{2}-\\d{4}\\b|\\b\\d{9}\\b', got %s", pattern.PatternText)
				}
			},
		},
		{
			name: "Update both pattern text and type",
			update: &models.SearchPatternUpdate{
				PatternType: string(models.CaseSensitive),
				PatternText: `\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b`,
			},
			expectError: false,
			check: func(t *testing.T, pattern *models.SearchPattern) {
				if pattern.PatternType != models.CaseSensitive {
					t.Errorf("Expected PatternType = %s, got %s", models.CaseSensitive, pattern.PatternType)
				}
				if pattern.PatternText != `\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b` {
				}
			},
		},
		{
			name: "Invalid pattern type",
			update: &models.SearchPatternUpdate{
				PatternType: "InvalidType",
			},
			expectError: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			updatedPattern, err := service.UpdateSearchPattern(context.Background(), userID, pattern.ID, tc.update)

			if tc.expectError {
				if err == nil {
					t.Error("Expected error, got nil")
				}
				return
			}

			if err != nil {
				t.Fatalf("UpdateSearchPattern() error = %v", err)
			}

			if updatedPattern == nil {
				t.Fatal("Expected non-nil pattern")
			}

			// Run checks
			tc.check(t, updatedPattern)

			// Verify that the pattern was updated in storage
			storedPattern, err := patternRepo.GetByID(context.Background(), pattern.ID)
			if err != nil {
				t.Fatalf("Failed to get stored pattern: %v", err)
			}

			// Run checks again on stored pattern
			tc.check(t, storedPattern)
		})
	}

	// Test error case - pattern not found
	_, err = service.UpdateSearchPattern(context.Background(), userID, int64(999), &models.SearchPatternUpdate{
		PatternText: "test",
	})
	if err == nil {
		t.Error("Expected error for non-existent pattern, got nil")
	}

	// Test error case - pattern belongs to different user
	newSettings, err := service.GetUserSettings(context.Background(), newUserID)
	if err != nil {
		t.Fatalf("Failed to get new user settings: %v", err)
	}

	otherPattern := models.NewSearchPattern(newSettings.ID, models.CaseSensitive, "test")
	err = patternRepo.Create(context.Background(), otherPattern)
	if err != nil {
		t.Fatalf("Failed to create pattern: %v", err)
	}

	_, err = service.UpdateSearchPattern(context.Background(), userID, otherPattern.ID, &models.SearchPatternUpdate{
		PatternText: "updated",
	})
	if err == nil {
		t.Error("Expected error when updating pattern belonging to different user, got nil")
	}
}

func TestSettingsService_DeleteSearchPattern(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	// Register valid user IDs
	userID := int64(123)
	newUserID := int64(456)
	settingsRepo.RegisterValidUserID(userID)
	settingsRepo.RegisterValidUserID(newUserID)

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	settings, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Create a pattern to delete
	pattern := models.NewSearchPattern(settings.ID, models.CaseSensitive, `\b\d{3}-\d{2}-\d{4}\b`)
	err = patternRepo.Create(context.Background(), pattern)
	if err != nil {
		t.Fatalf("Failed to create pattern: %v", err)
	}

	// Verify pattern was created
	patterns, err := service.GetSearchPatterns(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get patterns: %v", err)
	}
	if len(patterns) != 1 {
		t.Fatalf("Expected 1 pattern, got %d", len(patterns))
	}

	// Test deleting the pattern
	err = service.DeleteSearchPattern(context.Background(), userID, pattern.ID)
	if err != nil {
		t.Fatalf("DeleteSearchPattern() error = %v", err)
	}

	// Verify pattern was deleted
	patterns, err = service.GetSearchPatterns(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get patterns after deletion: %v", err)
	}
	if len(patterns) != 0 {
		t.Errorf("Expected 0 patterns after deletion, got %d", len(patterns))
	}

	// Test error case - deleting non-existent pattern
	err = service.DeleteSearchPattern(context.Background(), userID, int64(999))
	if err == nil {
		t.Error("Expected error when deleting non-existent pattern, got nil")
	}

	// Test error case - pattern belongs to different user
	newSettings, err := service.GetUserSettings(context.Background(), newUserID)
	if err != nil {
		t.Fatalf("Failed to get new user settings: %v", err)
	}

	otherPattern := models.NewSearchPattern(newSettings.ID, models.CaseSensitive, "test")
	err = patternRepo.Create(context.Background(), otherPattern)
	if err != nil {
		t.Fatalf("Failed to create pattern: %v", err)
	}

	err = service.DeleteSearchPattern(context.Background(), userID, otherPattern.ID)
	if err == nil {
		t.Error("Expected error when deleting pattern belonging to different user, got nil")
	}
}

func TestSettingsService_GetModelEntities(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	// Register valid user ID
	userID := int64(123)
	settingsRepo.RegisterValidUserID(userID)

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	settings, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Create some model entities
	methodID := int64(1)
	entity1 := models.NewModelEntity(settings.ID, methodID, "Entity 1")
	err = modelEntityRepo.Create(context.Background(), entity1)
	if err != nil {
		t.Fatalf("Failed to create entity: %v", err)
	}

	entity2 := models.NewModelEntity(settings.ID, methodID, "Entity 2")
	err = modelEntityRepo.Create(context.Background(), entity2)
	if err != nil {
		t.Fatalf("Failed to create entity: %v", err)
	}

	// Create an entity for a different method
	otherMethodID := int64(2)
	entity3 := models.NewModelEntity(settings.ID, otherMethodID, "Entity 3")
	err = modelEntityRepo.Create(context.Background(), entity3)
	if err != nil {
		t.Fatalf("Failed to create entity: %v", err)
	}

	// Test getting entities for method 1
	entities, err := service.GetModelEntities(context.Background(), userID, methodID)
	if err != nil {
		t.Fatalf("GetModelEntities() error = %v", err)
	}

	if len(entities) != 2 {
		t.Errorf("Expected 2 entities, got %d", len(entities))
	}

	// Verify entity details
	entityMap := make(map[int64]*models.ModelEntityWithMethod)
	for _, e := range entities {
		entityMap[e.ID] = e
	}

	e1 := entityMap[entity1.ID]
	if e1 == nil {
		t.Fatalf("Entity 1 not found in results")
	}
	if e1.EntityText != "Entity 1" {
		t.Errorf("Expected EntityText = 'Entity 1', got %s", e1.EntityText)
	}
	if e1.MethodID != methodID {
		t.Errorf("Expected MethodID = %d, got %d", methodID, e1.MethodID)
	}

	e2 := entityMap[entity2.ID]
	if e2 == nil {
		t.Fatalf("Entity 2 not found in results")
	}
	if e2.EntityText != "Entity 2" {
		t.Errorf("Expected EntityText = 'Entity 2', got %s", e2.EntityText)
	}
	if e2.MethodID != methodID {
		t.Errorf("Expected MethodID = %d, got %d", methodID, e2.MethodID)
	}

	// Test getting entities for method 2
	entities, err = service.GetModelEntities(context.Background(), userID, otherMethodID)
	if err != nil {
		t.Fatalf("GetModelEntities() error = %v", err)
	}

	if len(entities) != 1 {
		t.Errorf("Expected 1 entity, got %d", len(entities))
	}

	if entities[0].ID != entity3.ID {
		t.Errorf("Expected entity ID = %d, got %d", entity3.ID, entities[0].ID)
	}

	// Test getting entities for non-existent method
	entities, err = service.GetModelEntities(context.Background(), userID, int64(999))
	if err != nil {
		t.Fatalf("GetModelEntities() error = %v", err)
	}

	if len(entities) != 0 {
		t.Errorf("Expected 0 entities for non-existent method, got %d", len(entities))
	}

	// Test error case - user not found
	_, err = service.GetModelEntities(context.Background(), int64(999), methodID)
	if err == nil {
		t.Error("Expected error for non-existent user, got nil")
	}
}

func TestSettingsService_AddModelEntities(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	// Register valid user ID
	userID := int64(123)
	settingsRepo.RegisterValidUserID(userID)

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	_, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Test adding entities
	methodID := int64(1)
	entities := []string{"Phone Number", "Email Address", "IP Address"}

	batch := &models.ModelEntityBatch{
		MethodID:    methodID,
		EntityTexts: entities,
	}

	createdEntities, err := service.AddModelEntities(context.Background(), userID, batch)
	if err != nil {
		t.Fatalf("AddModelEntities() error = %v", err)
	}

	if len(createdEntities) != 3 {
		t.Errorf("Expected 3 created entities, got %d", len(createdEntities))
	}

	// Verify entity details
	for i, entity := range createdEntities {
		if entity.MethodID != methodID {
			t.Errorf("Entity %d: Expected MethodID = %d, got %d", i, methodID, entity.MethodID)
		}
		if entity.EntityText != entities[i] {
			t.Errorf("Entity %d: Expected EntityText = %s, got %s", i, entities[i], entity.EntityText)
		}
	}

	// Verify entities were stored
	storedEntities, err := service.GetModelEntities(context.Background(), userID, methodID)
	if err != nil {
		t.Fatalf("Failed to get stored entities: %v", err)
	}

	if len(storedEntities) != 3 {
		t.Errorf("Expected 3 stored entities, got %d", len(storedEntities))
	}

	// Add more entities
	moreEntities := []string{"Credit Card", "SSN"}
	batch.EntityTexts = moreEntities

	createdEntities, err = service.AddModelEntities(context.Background(), userID, batch)
	if err != nil {
		t.Fatalf("AddModelEntities() error = %v", err)
	}

	if len(createdEntities) != 2 {
		t.Errorf("Expected 2 more created entities, got %d", len(createdEntities))
	}

	// Verify all entities are stored
	storedEntities, err = service.GetModelEntities(context.Background(), userID, methodID)
	if err != nil {
		t.Fatalf("Failed to get stored entities: %v", err)
	}

	if len(storedEntities) != 5 {
		t.Errorf("Expected 5 total stored entities, got %d", len(storedEntities))
	}

	// Test error case - user not found
	_, err = service.AddModelEntities(context.Background(), int64(999), batch)
	if err == nil {
		t.Error("Expected error for non-existent user, got nil")
	}
}

func TestSettingsService_DeleteModelEntity(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	// Register valid user IDs
	userID := int64(123)
	newUserID := int64(456)
	settingsRepo.RegisterValidUserID(userID)
	settingsRepo.RegisterValidUserID(newUserID)

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	settings, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Create a model entity to delete
	methodID := int64(1)
	entity := models.NewModelEntity(settings.ID, methodID, "Test Entity")
	err = modelEntityRepo.Create(context.Background(), entity)
	if err != nil {
		t.Fatalf("Failed to create entity: %v", err)
	}

	// Verify entity was created
	entities, err := service.GetModelEntities(context.Background(), userID, methodID)
	if err != nil {
		t.Fatalf("Failed to get entities: %v", err)
	}
	if len(entities) != 1 {
		t.Fatalf("Expected 1 entity, got %d", len(entities))
	}

	// Test deleting the entity
	err = service.DeleteModelEntity(context.Background(), userID, entity.ID)
	if err != nil {
		t.Fatalf("DeleteModelEntity() error = %v", err)
	}

	// Verify entity was deleted
	entities, err = service.GetModelEntities(context.Background(), userID, methodID)
	if err != nil {
		t.Fatalf("Failed to get entities after deletion: %v", err)
	}
	if len(entities) != 0 {
		t.Errorf("Expected 0 entities after deletion, got %d", len(entities))
	}

	// Test error case - deleting non-existent entity
	err = service.DeleteModelEntity(context.Background(), userID, int64(999))
	if err == nil {
		t.Error("Expected error when deleting non-existent entity, got nil")
	}

	// Test error case - entity belongs to different user
	newSettings, err := service.GetUserSettings(context.Background(), newUserID)
	if err != nil {
		t.Fatalf("Failed to get new user settings: %v", err)
	}

	otherEntity := models.NewModelEntity(newSettings.ID, methodID, "Other Entity")
	err = modelEntityRepo.Create(context.Background(), otherEntity)
	if err != nil {
		t.Fatalf("Failed to create entity: %v", err)
	}

	err = service.DeleteModelEntity(context.Background(), userID, otherEntity.ID)
	if err == nil {
		t.Error("Expected error when deleting entity belonging to different user, got nil")
	}
}

// Helper functions for creating pointers to primitives
func boolPtr(b bool) *bool {
	return &b
}

func stringPtr(s string) *string {
	return &s
}

func float64Ptr(f float64) *float64 {
	return &f
}
