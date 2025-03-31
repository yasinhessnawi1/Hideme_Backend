package service

import (
	"context"
	"fmt"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
	"testing"
)

// Mock implementations for testing
type MockSettingsRepository struct {
	settings map[int64]*models.UserSetting
	nextID   int64
}

func NewMockSettingsRepository() *MockSettingsRepository {
	return &MockSettingsRepository{
		settings: make(map[int64]*models.UserSetting),
		nextID:   1,
	}
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

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Test getting settings for a user without settings
	userID := int64(123)
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
}

func TestSettingsService_UpdateUserSettings(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get default settings for a user
	userID := int64(123)
	settings, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Check default value
	if settings.RemoveImages {
		t.Error("Expected RemoveImages to default to false")
	}

	// Update settings
	removeImages := true
	update := &models.UserSettingsUpdate{
		RemoveImages: &removeImages,
	}

	updatedSettings, err := service.UpdateUserSettings(context.Background(), userID, update)

	// Check results
	if err != nil {
		t.Errorf("UpdateUserSettings() error = %v", err)
	}

	if updatedSettings == nil {
		t.Fatal("Expected non-nil settings")
	}

	if !updatedSettings.RemoveImages {
		t.Error("Expected RemoveImages to be updated to true")
	}

	// Check that settings were updated in the repository
	storedSettings, err := settingsRepo.GetByUserID(context.Background(), userID)
	if err != nil {
		t.Errorf("Failed to get stored settings: %v", err)
	}

	if !storedSettings.RemoveImages {
		t.Error("Expected stored RemoveImages to be updated to true")
	}

	// Test updating for a user without settings
	newUserID := int64(456)
	removeImages = false
	update.RemoveImages = &removeImages

	updatedSettings, err = service.UpdateUserSettings(context.Background(), newUserID, update)

	// Check that settings were created and updated
	if err != nil {
		t.Errorf("UpdateUserSettings() error = %v", err)
	}

	if updatedSettings.RemoveImages {
		t.Error("Expected RemoveImages to be updated to false")
	}
}

func TestSettingsService_GetBanList(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	userID := int64(123)
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
	newUserID := int64(456)
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
}

func TestSettingsService_AddBanListWords(t *testing.T) {

}

func TestSettingsService_RemoveBanListWords(t *testing.T) {

}

func TestSettingsService_GetSearchPatterns(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	userID := int64(123)
	settings, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Create some patterns
	pattern1 := &models.SearchPattern{
		SettingID:   settings.ID,
		PatternType: models.PatternTypeRegex,
		PatternText: "\\d{3}-\\d{2}-\\d{4}", // SSN pattern
	}

	err = patternRepo.Create(context.Background(), pattern1)
	if err != nil {
		t.Fatalf("Failed to create pattern: %v", err)
	}

	pattern2 := &models.SearchPattern{
		SettingID:   settings.ID,
		PatternType: models.PatternTypeNormal,
		PatternText: "confidential",
	}

	err = patternRepo.Create(context.Background(), pattern2)
	if err != nil {
		t.Fatalf("Failed to create pattern: %v", err)
	}

	// Get search patterns
	patterns, err := service.GetSearchPatterns(context.Background(), userID)

	// Check results
	if err != nil {
		t.Errorf("GetSearchPatterns() error = %v", err)
	}

	if len(patterns) != 2 {
		t.Errorf("Expected 2 patterns, got %d", len(patterns))
	}

	// Test getting patterns for a user without settings
	newUserID := int64(456)
	patterns, err = service.GetSearchPatterns(context.Background(), newUserID)

	// Check that we get an empty slice
	if err != nil {
		t.Errorf("GetSearchPatterns() error = %v", err)
	}

	if len(patterns) != 0 {
		t.Errorf("Expected 0 patterns, got %d", len(patterns))
	}
}

func TestSettingsService_CreateSearchPattern(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	userID := int64(123)
	_, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Create a search pattern
	patternCreate := &models.SearchPatternCreate{
		PatternType: "Regex",
		PatternText: "\\d{3}-\\d{2}-\\d{4}", // SSN pattern
	}

	pattern, err := service.CreateSearchPattern(context.Background(), userID, patternCreate)

	// Check results
	if err != nil {
		t.Errorf("CreateSearchPattern() error = %v", err)
	}

	if pattern == nil {
		t.Fatal("Expected non-nil pattern")
	}

	if pattern.PatternType != models.PatternTypeRegex {
		t.Errorf("Expected PatternType = %s, got %s", models.PatternTypeRegex, pattern.PatternType)
	}

	if pattern.PatternText != patternCreate.PatternText {
		t.Errorf("Expected PatternText = %s, got %s", patternCreate.PatternText, pattern.PatternText)
	}

	// Get patterns to verify it was stored
	patterns, err := service.GetSearchPatterns(context.Background(), userID)
	if err != nil {
		t.Errorf("Failed to get patterns: %v", err)
	}

	if len(patterns) != 1 {
		t.Errorf("Expected 1 pattern, got %d", len(patterns))
	}

	// Test with invalid pattern type
	invalidPattern := &models.SearchPatternCreate{
		PatternType: "Invalid",
		PatternText: "test",
	}

	_, err = service.CreateSearchPattern(context.Background(), userID, invalidPattern)

	// Check that we get a validation error
	if err == nil {
		t.Error("Expected error for invalid pattern type")
	}
}

func TestSettingsService_UpdateSearchPattern(t *testing.T) {
	// Setup
	settingsRepo := NewMockSettingsRepository()
	banListRepo := NewMockBanListRepository()
	patternRepo := NewMockPatternRepository()
	modelEntityRepo := NewMockModelEntityRepository()

	service := NewSettingsService(settingsRepo, banListRepo, patternRepo, modelEntityRepo)

	// Get settings for a user
	userID := int64(123)
	settings, err := service.GetUserSettings(context.Background(), userID)
	if err != nil {
		t.Fatalf("Failed to get user settings: %v", err)
	}

	// Create a pattern
	pattern := &models.SearchPattern{
		SettingID:   settings.ID,
		PatternType: models.PatternTypeRegex,
		PatternText: "\\d{3}-\\d{2}-\\d{4}", // SSN pattern
	}

	err = patternRepo.Create(context.Background(), pattern)
	if err != nil {
		t.Fatalf("Failed to create pattern: %v", err)
	}

	// Update the pattern
	patternUpdate := &models.SearchPatternUpdate{
		PatternType: "Normal",
		PatternText: "Updated Text",
	}

	updatedPattern, err := service.UpdateSearchPattern(context.Background(), userID, pattern.ID, patternUpdate)

	// Check results
	if err != nil {
		t.Errorf("UpdateSearchPattern() error = %v", err)
	}

	if updatedPattern == nil {
		t.Fatal("Expected non-nil pattern")
	}

	if updatedPattern.PatternType != models.PatternTypeNormal {
		t.Errorf("Expected PatternType = %s, got %s", models.PatternTypeNormal, updatedPattern.PatternType)
	}

	if updatedPattern.PatternText != patternUpdate.PatternText {
		t.Errorf("Expected PatternText = %s, got %s", patternUpdate.PatternText, updatedPattern.PatternText)
	}

	// Get the pattern to verify it was updated
	retrievedPattern, err := patternRepo.GetByID(context.Background(), pattern.ID)
	if err != nil {
		t.Errorf("Failed to get pattern: %v", err)
	}

	if retrievedPattern.PatternType != models.PatternTypeNormal {
		t.Errorf("Expected stored PatternType = %s, got %s", models.PatternTypeNormal, retrievedPattern.PatternType)
	}

	// Test updating with invalid pattern type
	invalidUpdate := &models.SearchPatternUpdate{
		PatternType: "Invalid",
	}

	_, err = service.UpdateSearchPattern(context.Background(), userID, pattern.ID, invalidUpdate)

	// Check that we get a validation error
	if err == nil {
		t.Error("Expected error for invalid pattern type")
	}

	// Test updating a pattern that doesn't exist
	_, err = service.UpdateSearchPattern(context.Background(), userID, 999, patternUpdate)

	// Check that we get a not found error
	if err == nil {
		t.Error("Expected error for non-existent pattern")
	}

	// Create another user and pattern
	otherUserID := int64(456)
	otherSettings, err := service.GetUserSettings(context.Background(), otherUserID)
	if err != nil {
		t.Fatalf("Failed to get other user settings: %v", err)
	}

	otherPattern := &models.SearchPattern{
		SettingID:   otherSettings.ID,
		PatternType: models.PatternTypeNormal,
		PatternText: "Other Pattern",
	}

	err = patternRepo.Create(context.Background(), otherPattern)
	if err != nil {
		t.Fatalf("Failed to create other pattern: %v", err)
	}

	// Test updating someone else's pattern
	_, err = service.UpdateSearchPattern(context.Background(), userID, otherPattern.ID, patternUpdate)

	// Check that we get a forbidden error
	if err == nil {
		t.Error("Expected error for updating someone else's pattern")
	}
}
