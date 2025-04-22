package handlers_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strconv"
	"testing"

	"github.com/go-chi/chi/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/handlers"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
)

// MockSettingsService is a mock implementation of the SettingsService
type MockSettingsService struct {
	mock.Mock
}

func (m *MockSettingsService) GetUserSettings(ctx context.Context, userID int64) (*models.UserSetting, error) {
	args := m.Called(ctx, userID)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.UserSetting), args.Error(1)
}

func (m *MockSettingsService) UpdateUserSettings(ctx context.Context, userID int64, update *models.UserSettingsUpdate) (*models.UserSetting, error) {
	args := m.Called(ctx, userID, update)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.UserSetting), args.Error(1)
}

func (m *MockSettingsService) GetBanList(ctx context.Context, userID int64) (*models.BanListWithWords, error) {
	args := m.Called(ctx, userID)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.BanListWithWords), args.Error(1)
}

func (m *MockSettingsService) AddBanListWords(ctx context.Context, userID int64, words []string) error {
	args := m.Called(ctx, userID, words)
	return args.Error(0)
}

func (m *MockSettingsService) RemoveBanListWords(ctx context.Context, userID int64, words []string) error {
	args := m.Called(ctx, userID, words)
	return args.Error(0)
}

func (m *MockSettingsService) GetSearchPatterns(ctx context.Context, userID int64) ([]*models.SearchPattern, error) {
	args := m.Called(ctx, userID)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]*models.SearchPattern), args.Error(1)
}

func (m *MockSettingsService) CreateSearchPattern(ctx context.Context, userID int64, pattern *models.SearchPatternCreate) (*models.SearchPattern, error) {
	args := m.Called(ctx, userID, pattern)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.SearchPattern), args.Error(1)
}

func (m *MockSettingsService) UpdateSearchPattern(ctx context.Context, userID int64, patternID int64, update *models.SearchPatternUpdate) (*models.SearchPattern, error) {
	args := m.Called(ctx, userID, patternID, update)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.SearchPattern), args.Error(1)
}

func (m *MockSettingsService) DeleteSearchPattern(ctx context.Context, userID int64, patternID int64) error {
	args := m.Called(ctx, userID, patternID)
	return args.Error(0)
}

func (m *MockSettingsService) GetModelEntities(ctx context.Context, userID int64, methodID int64) ([]*models.ModelEntityWithMethod, error) {
	args := m.Called(ctx, userID, methodID)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]*models.ModelEntityWithMethod), args.Error(1)
}

func (m *MockSettingsService) AddModelEntities(ctx context.Context, userID int64, batch *models.ModelEntityBatch) ([]*models.ModelEntity, error) {
	args := m.Called(ctx, userID, batch)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).([]*models.ModelEntity), args.Error(1)
}

func (m *MockSettingsService) DeleteModelEntity(ctx context.Context, userID int64, entityID int64) error {
	args := m.Called(ctx, userID, entityID)
	return args.Error(0)
}

func (m *MockSettingsService) DeleteModelEntityByMethodID(ctx context.Context, userID int64, methodID int64) error {
	args := m.Called(ctx, userID, methodID)
	return args.Error(0)
}

// Add to your MockSettingsService struct
func (m *MockSettingsService) ExportSettings(ctx context.Context, userID int64) (*models.SettingsExport, error) {
	// For tests, you can return a simple implementation or nil
	args := m.Called(ctx, userID)
	if args.Get(0) == nil {
		return nil, args.Error(1)
	}
	return args.Get(0).(*models.SettingsExport), args.Error(1)
}

func (m *MockSettingsService) ImportSettings(ctx context.Context, userID int64, importData *models.SettingsExport) error {
	args := m.Called(ctx, userID, importData)
	return args.Error(0)
}

// Helper functions for testing
func setupSettingsTest(t *testing.T) (*handlers.SettingsHandler, *MockSettingsService) {
	mockService := new(MockSettingsService)
	handler := handlers.NewSettingsHandler(mockService)
	return handler, mockService
}

func createAuthContext(userID int64) context.Context {
	ctx := context.Background()
	return context.WithValue(ctx, auth.UserIDContextKey, userID)
}

func TestGetSettings(t *testing.T) {
	// Setup
	handler, mockService := setupSettingsTest(t)

	// Test successful case
	t.Run("Success", func(t *testing.T) {
		// Create expected settings
		expectedSettings := &models.UserSetting{
			ID:                     1,
			UserID:                 1001,
			RemoveImages:           true,
			Theme:                  "dark",
			AutoProcessing:         true,
			DetectionThreshold:     0.75,
			UseBanlistForDetection: true,
		}

		// Setup mock service
		mockService.On("GetUserSettings", mock.Anything, int64(1001)).Return(expectedSettings, nil).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/settings", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetSettings(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool               `json:"success"`
			Data    models.UserSetting `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content using the data field from the wrapper
		assert.Equal(t, expectedSettings.ID, responseWrapper.Data.ID)
		assert.Equal(t, expectedSettings.UserID, responseWrapper.Data.UserID)
		assert.Equal(t, expectedSettings.RemoveImages, responseWrapper.Data.RemoveImages)
		assert.Equal(t, expectedSettings.Theme, responseWrapper.Data.Theme)
		assert.Equal(t, expectedSettings.AutoProcessing, responseWrapper.Data.AutoProcessing)
		assert.Equal(t, expectedSettings.DetectionThreshold, responseWrapper.Data.DetectionThreshold)
		assert.Equal(t, expectedSettings.UseBanlistForDetection, responseWrapper.Data.UseBanlistForDetection)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create test request without auth context
		req, err := http.NewRequest("GET", "/api/settings", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetSettings(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Setup mock service to return error
		mockService.On("GetUserSettings", mock.Anything, int64(1001)).Return(nil, errors.New("service error")).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/settings", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetSettings(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

func TestUpdateSettings(t *testing.T) {
	// Setup
	handler, mockService := setupSettingsTest(t)

	// Test successful case
	t.Run("Success", func(t *testing.T) {
		// Create request payload
		removeImages := false
		theme := "light"
		autoProcessing := false
		detectThreshold := 0.85
		useBanlist := true

		update := models.UserSettingsUpdate{
			RemoveImages:           &removeImages,
			Theme:                  &theme,
			AutoProcessing:         &autoProcessing,
			DetectionThreshold:     &detectThreshold,
			UseBanlistForDetection: &useBanlist,
		}

		// Expected updated settings
		expectedSettings := &models.UserSetting{
			ID:                     1,
			UserID:                 1001,
			RemoveImages:           removeImages,
			Theme:                  theme,
			AutoProcessing:         autoProcessing,
			DetectionThreshold:     detectThreshold,
			UseBanlistForDetection: useBanlist,
		}

		// Setup mock service
		mockService.On("UpdateUserSettings", mock.Anything, int64(1001), mock.MatchedBy(func(u *models.UserSettingsUpdate) bool {
			return *u.RemoveImages == removeImages &&
				*u.Theme == theme &&
				*u.AutoProcessing == autoProcessing &&
				*u.DetectionThreshold == detectThreshold &&
				*u.UseBanlistForDetection == useBanlist
		})).Return(expectedSettings, nil).Once()

		// Create request body
		requestBody, err := json.Marshal(update)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("PUT", "/api/settings", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.UpdateSettings(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool               `json:"success"`
			Data    models.UserSetting `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content using the data field from the wrapper
		assert.Equal(t, expectedSettings.ID, responseWrapper.Data.ID)
		assert.Equal(t, expectedSettings.UserID, responseWrapper.Data.UserID)
		assert.Equal(t, expectedSettings.RemoveImages, responseWrapper.Data.RemoveImages)
		assert.Equal(t, expectedSettings.Theme, responseWrapper.Data.Theme)
		assert.Equal(t, expectedSettings.AutoProcessing, responseWrapper.Data.AutoProcessing)
		assert.Equal(t, expectedSettings.DetectionThreshold, responseWrapper.Data.DetectionThreshold)
		assert.Equal(t, expectedSettings.UseBanlistForDetection, responseWrapper.Data.UseBanlistForDetection)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid Request Body", func(t *testing.T) {
		// Create invalid JSON
		invalidJSON := []byte(`{"theme": invalid}`)

		// Create test request
		req, err := http.NewRequest("PUT", "/api/settings", bytes.NewBuffer(invalidJSON))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.UpdateSettings(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create valid request body
		update := models.UserSettingsUpdate{
			Theme: stringPtr("light"),
		}
		requestBody, err := json.Marshal(update)
		require.NoError(t, err)

		// Create test request without auth context
		req, err := http.NewRequest("PUT", "/api/settings", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.UpdateSettings(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Create request payload
		theme := "light"
		update := models.UserSettingsUpdate{
			Theme: &theme,
		}

		// Setup mock service to return error
		mockService.On("UpdateUserSettings", mock.Anything, int64(1001), mock.MatchedBy(func(u *models.UserSettingsUpdate) bool {
			return *u.Theme == theme
		})).Return(nil, errors.New("service error")).Once()

		// Create request body
		requestBody, err := json.Marshal(update)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("PUT", "/api/settings", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.UpdateSettings(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

func TestGetBanList(t *testing.T) {
	// Setup
	handler, mockService := setupSettingsTest(t)

	// Test successful case
	t.Run("Success", func(t *testing.T) {
		// Create expected ban list
		expectedBanList := &models.BanListWithWords{
			ID:    1,
			Words: []string{"word1", "word2", "word3"},
		}

		// Setup mock service
		mockService.On("GetBanList", mock.Anything, int64(1001)).Return(expectedBanList, nil).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/settings/ban-list", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetBanList(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool                    `json:"success"`
			Data    models.BanListWithWords `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content using the data field from the wrapper
		assert.Equal(t, expectedBanList.ID, responseWrapper.Data.ID)
		assert.ElementsMatch(t, expectedBanList.Words, responseWrapper.Data.Words)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create test request without auth context
		req, err := http.NewRequest("GET", "/api/settings/ban-list", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetBanList(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Setup mock service to return error
		mockService.On("GetBanList", mock.Anything, int64(1001)).Return(nil, errors.New("service error")).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/settings/ban-list", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetBanList(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

func TestAddBanListWords(t *testing.T) {
	// Setup
	handler, mockService := setupSettingsTest(t)

	// Test successful case
	t.Run("Success", func(t *testing.T) {
		// Create request payload
		batch := models.BanListWordBatch{
			Words: []string{"word4", "word5"},
		}

		// Expected response after adding words
		expectedBanList := &models.BanListWithWords{
			ID:    1,
			Words: []string{"word1", "word2", "word3", "word4", "word5"},
		}

		// Setup mock service expectations
		mockService.On("AddBanListWords", mock.Anything, int64(1001), batch.Words).Return(nil).Once()
		mockService.On("GetBanList", mock.Anything, int64(1001)).Return(expectedBanList, nil).Once()

		// Create request body
		requestBody, err := json.Marshal(batch)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("POST", "/api/settings/ban-list/words", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.AddBanListWords(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool                    `json:"success"`
			Data    models.BanListWithWords `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content using the data field from the wrapper
		assert.Equal(t, expectedBanList.ID, responseWrapper.Data.ID)
		assert.ElementsMatch(t, expectedBanList.Words, responseWrapper.Data.Words)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid Request Body", func(t *testing.T) {
		// Create invalid JSON
		invalidJSON := []byte(`{"words": [invalid]}`)

		// Create test request
		req, err := http.NewRequest("POST", "/api/settings/ban-list/words", bytes.NewBuffer(invalidJSON))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.AddBanListWords(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create valid request body
		batch := models.BanListWordBatch{
			Words: []string{"word4", "word5"},
		}
		requestBody, err := json.Marshal(batch)
		require.NoError(t, err)

		// Create test request without auth context
		req, err := http.NewRequest("POST", "/api/settings/ban-list/words", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.AddBanListWords(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error - AddBanListWords", func(t *testing.T) {
		// Create request payload
		batch := models.BanListWordBatch{
			Words: []string{"word4", "word5"},
		}

		// Setup mock service to return error
		mockService.On("AddBanListWords", mock.Anything, int64(1001), batch.Words).
			Return(errors.New("service error")).Once()

		// Create request body
		requestBody, err := json.Marshal(batch)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("POST", "/api/settings/ban-list/words", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.AddBanListWords(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Service Error - GetBanList", func(t *testing.T) {
		// Create request payload
		batch := models.BanListWordBatch{
			Words: []string{"word4", "word5"},
		}

		// Setup mock service expectations
		mockService.On("AddBanListWords", mock.Anything, int64(1001), batch.Words).Return(nil).Once()
		mockService.On("GetBanList", mock.Anything, int64(1001)).
			Return(nil, errors.New("service error")).Once()

		// Create request body
		requestBody, err := json.Marshal(batch)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("POST", "/api/settings/ban-list/words", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.AddBanListWords(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

func TestRemoveBanListWords(t *testing.T) {
	// Setup
	handler, mockService := setupSettingsTest(t)

	// Test successful case
	t.Run("Success", func(t *testing.T) {
		// Create request payload
		batch := models.BanListWordBatch{
			Words: []string{"word1", "word2"},
		}

		// Expected response after removing words
		expectedBanList := &models.BanListWithWords{
			ID:    1,
			Words: []string{"word3"},
		}

		// Setup mock service expectations
		mockService.On("RemoveBanListWords", mock.Anything, int64(1001), batch.Words).Return(nil).Once()
		mockService.On("GetBanList", mock.Anything, int64(1001)).Return(expectedBanList, nil).Once()

		// Create request body
		requestBody, err := json.Marshal(batch)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("DELETE", "/api/settings/ban-list/words", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.RemoveBanListWords(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define response wrapper to handle the JSON envelope format
		var responseWrapper struct {
			Success bool                    `json:"success"`
			Data    models.BanListWithWords `json:"data"`
		}

		// Parse response body into wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content using the data field from the wrapper
		assert.Equal(t, expectedBanList.ID, responseWrapper.Data.ID)
		assert.ElementsMatch(t, expectedBanList.Words, responseWrapper.Data.Words)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid Request Body", func(t *testing.T) {
		// Create invalid JSON
		invalidJSON := []byte(`{"words": [invalid]}`)

		// Create test request
		req, err := http.NewRequest("DELETE", "/api/settings/ban-list/words", bytes.NewBuffer(invalidJSON))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.RemoveBanListWords(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create valid request body
		batch := models.BanListWordBatch{
			Words: []string{"word1", "word2"},
		}
		requestBody, err := json.Marshal(batch)
		require.NoError(t, err)

		// Create test request without auth context
		req, err := http.NewRequest("DELETE", "/api/settings/ban-list/words", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.RemoveBanListWords(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error - RemoveBanListWords", func(t *testing.T) {
		// Create request payload
		batch := models.BanListWordBatch{
			Words: []string{"word1", "word2"},
		}

		// Setup mock service to return error
		mockService.On("RemoveBanListWords", mock.Anything, int64(1001), batch.Words).
			Return(errors.New("service error")).Once()

		// Create request body
		requestBody, err := json.Marshal(batch)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("DELETE", "/api/settings/ban-list/words", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.RemoveBanListWords(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

func TestGetSearchPatterns(t *testing.T) {
	// Setup
	handler, mockService := setupSettingsTest(t)

	// Test successful case
	t.Run("Success", func(t *testing.T) {
		// Create expected search patterns
		expectedPatterns := []*models.SearchPattern{
			{
				ID:          1,
				SettingID:   1,
				PatternType: "normal",
				PatternText: "pattern1",
			},
			{
				ID:          2,
				SettingID:   1,
				PatternType: "case_sensitive",
				PatternText: "pattern2",
			},
		}

		// Setup mock service
		mockService.On("GetSearchPatterns", mock.Anything, int64(1001)).Return(expectedPatterns, nil).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/settings/patterns", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetSearchPatterns(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool                    `json:"success"`
			Data    []*models.SearchPattern `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content using the data field from the wrapper
		assert.Equal(t, len(expectedPatterns), len(responseWrapper.Data))
		for i, pattern := range expectedPatterns {
			assert.Equal(t, pattern.ID, responseWrapper.Data[i].ID)
			assert.Equal(t, pattern.SettingID, responseWrapper.Data[i].SettingID)
			assert.Equal(t, pattern.PatternType, responseWrapper.Data[i].PatternType)
			assert.Equal(t, pattern.PatternText, responseWrapper.Data[i].PatternText)
		}

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create test request without auth context
		req, err := http.NewRequest("GET", "/api/settings/patterns", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetSearchPatterns(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Setup mock service to return error
		mockService.On("GetSearchPatterns", mock.Anything, int64(1001)).Return(nil, errors.New("service error")).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/settings/patterns", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.GetSearchPatterns(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

func TestCreateSearchPattern(t *testing.T) {
	// Setup
	handler, mockService := setupSettingsTest(t)

	// Test successful case
	t.Run("Success", func(t *testing.T) {
		// Create request payload
		pattern := models.SearchPatternCreate{
			PatternType: "normal",
			PatternText: "new pattern",
		}

		// Expected created pattern
		expectedPattern := &models.SearchPattern{
			ID:          3,
			SettingID:   1,
			PatternType: "normal",
			PatternText: "new pattern",
		}

		// Setup mock service
		mockService.On("CreateSearchPattern", mock.Anything, int64(1001), mock.MatchedBy(func(p *models.SearchPatternCreate) bool {
			return p.PatternType == pattern.PatternType && p.PatternText == pattern.PatternText
		})).Return(expectedPattern, nil).Once()

		// Create request body
		requestBody, err := json.Marshal(pattern)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("POST", "/api/settings/patterns", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CreateSearchPattern(rr, req)

		// Verify response
		assert.Equal(t, http.StatusCreated, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool                 `json:"success"`
			Data    models.SearchPattern `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content using the data field from the wrapper
		assert.Equal(t, expectedPattern.ID, responseWrapper.Data.ID)
		assert.Equal(t, expectedPattern.SettingID, responseWrapper.Data.SettingID)
		assert.Equal(t, expectedPattern.PatternType, responseWrapper.Data.PatternType)
		assert.Equal(t, expectedPattern.PatternText, responseWrapper.Data.PatternText)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid Request Body", func(t *testing.T) {
		// Create invalid JSON
		invalidJSON := []byte(`{"pattern_type": invalid}`)

		// Create test request
		req, err := http.NewRequest("POST", "/api/settings/patterns", bytes.NewBuffer(invalidJSON))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CreateSearchPattern(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create valid request body
		pattern := models.SearchPatternCreate{
			PatternType: "normal",
			PatternText: "new pattern",
		}
		requestBody, err := json.Marshal(pattern)
		require.NoError(t, err)

		// Create test request without auth context
		req, err := http.NewRequest("POST", "/api/settings/patterns", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CreateSearchPattern(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Create request payload
		pattern := models.SearchPatternCreate{
			PatternType: "normal",
			PatternText: "new pattern",
		}

		// Setup mock service to return error
		mockService.On("CreateSearchPattern", mock.Anything, int64(1001), mock.MatchedBy(func(p *models.SearchPatternCreate) bool {
			return p.PatternType == pattern.PatternType && p.PatternText == pattern.PatternText
		})).Return(nil, errors.New("service error")).Once()

		// Create request body
		requestBody, err := json.Marshal(pattern)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("POST", "/api/settings/patterns", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.CreateSearchPattern(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

func TestUpdateSearchPattern(t *testing.T) {
	// Setup
	handler, mockService := setupSettingsTest(t)
	router := chi.NewRouter()
	router.Put("/api/settings/patterns/{patternID}", handler.UpdateSearchPattern)

	// Test successful case
	t.Run("Success", func(t *testing.T) {
		// Create request payload
		patternID := int64(123)
		update := models.SearchPatternUpdate{
			PatternType: "ai_search",
			PatternText: "updated pattern",
		}

		// Expected updated pattern
		expectedPattern := &models.SearchPattern{
			ID:          patternID,
			SettingID:   1,
			PatternType: "ai_search",
			PatternText: "updated pattern",
		}

		// Setup mock service
		mockService.On("UpdateSearchPattern", mock.Anything, int64(1001), patternID, mock.MatchedBy(func(u *models.SearchPatternUpdate) bool {
			return u.PatternType == update.PatternType && u.PatternText == update.PatternText
		})).Return(expectedPattern, nil).Once()

		// Create request body
		requestBody, err := json.Marshal(update)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("PUT", "/api/settings/patterns/"+strconv.FormatInt(patternID, 10), bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router to process URL parameters
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool                 `json:"success"`
			Data    models.SearchPattern `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content using the data field from the wrapper
		assert.Equal(t, expectedPattern.ID, responseWrapper.Data.ID)
		assert.Equal(t, expectedPattern.SettingID, responseWrapper.Data.SettingID)
		assert.Equal(t, expectedPattern.PatternType, responseWrapper.Data.PatternType)
		assert.Equal(t, expectedPattern.PatternText, responseWrapper.Data.PatternText)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid Pattern ID", func(t *testing.T) {
		// Create valid request body
		update := models.SearchPatternUpdate{
			PatternType: "normal",
			PatternText: "updated pattern",
		}
		requestBody, err := json.Marshal(update)
		require.NoError(t, err)

		// Create test request with invalid pattern ID
		req, err := http.NewRequest("PUT", "/api/settings/patterns/invalid", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Invalid Request Body", func(t *testing.T) {
		// Create invalid JSON
		invalidJSON := []byte(`{"pattern_type": invalid}`)

		// Create test request
		req, err := http.NewRequest("PUT", "/api/settings/patterns/123", bytes.NewBuffer(invalidJSON))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create valid request body
		update := models.SearchPatternUpdate{
			PatternType: "normal",
			PatternText: "updated pattern",
		}
		requestBody, err := json.Marshal(update)
		require.NoError(t, err)

		// Create test request without auth context
		req, err := http.NewRequest("PUT", "/api/settings/patterns/123", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via the handler directly to test auth check
		handler.UpdateSearchPattern(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Create request payload
		patternID := int64(123)
		update := models.SearchPatternUpdate{
			PatternType: "normal",
			PatternText: "updated pattern",
		}

		// Setup mock service to return error
		mockService.On("UpdateSearchPattern", mock.Anything, int64(1001), patternID, mock.MatchedBy(func(u *models.SearchPatternUpdate) bool {
			return u.PatternType == update.PatternType && u.PatternText == update.PatternText
		})).Return(nil, errors.New("service error")).Once()

		// Create request body
		requestBody, err := json.Marshal(update)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("PUT", "/api/settings/patterns/"+strconv.FormatInt(patternID, 10), bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

func TestDeleteSearchPattern(t *testing.T) {
	// Setup
	handler, mockService := setupSettingsTest(t)
	router := chi.NewRouter()
	router.Delete("/api/settings/patterns/{patternID}", handler.DeleteSearchPattern)

	// Test successful case
	t.Run("Success", func(t *testing.T) {
		// Create pattern ID
		patternID := int64(123)

		// Setup mock service
		mockService.On("DeleteSearchPattern", mock.Anything, int64(1001), patternID).Return(nil).Once()

		// Create test request
		req, err := http.NewRequest("DELETE", "/api/settings/patterns/"+strconv.FormatInt(patternID, 10), nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusNoContent, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid Pattern ID", func(t *testing.T) {
		// Create test request with invalid pattern ID
		req, err := http.NewRequest("DELETE", "/api/settings/patterns/invalid", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create test request without auth context
		req, err := http.NewRequest("DELETE", "/api/settings/patterns/123", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler directly to test auth check
		handler.DeleteSearchPattern(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Create pattern ID
		patternID := int64(123)

		// Setup mock service to return error
		mockService.On("DeleteSearchPattern", mock.Anything, int64(1001), patternID).
			Return(errors.New("service error")).Once()

		// Create test request
		req, err := http.NewRequest("DELETE", "/api/settings/patterns/"+strconv.FormatInt(patternID, 10), nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

func TestGetModelEntities(t *testing.T) {
	// Setup
	handler, mockService := setupSettingsTest(t)
	router := chi.NewRouter()
	router.Get("/api/settings/entities/{methodID}", handler.GetModelEntities)

	// Test successful case
	t.Run("Success", func(t *testing.T) {
		// Create method ID
		methodID := int64(1)

		// Expected entities
		expectedEntities := []*models.ModelEntityWithMethod{
			{
				ModelEntity: models.ModelEntity{ // Explicitly initialize the embedded struct
					ID:         1,
					SettingID:  1,
					MethodID:   methodID,
					EntityText: "Entity 1",
				},
				MethodName: "Method 1",
			},
			{
				ModelEntity: models.ModelEntity{
					ID:         2,
					SettingID:  1,
					MethodID:   methodID,
					EntityText: "Entity 2",
				},
				MethodName: "Method 1",
			},
		}

		// Setup mock service
		mockService.On("GetModelEntities", mock.Anything, int64(1001), methodID).
			Return(expectedEntities, nil).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/settings/entities/"+strconv.FormatInt(methodID, 10), nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusOK, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool                            `json:"success"`
			Data    []*models.ModelEntityWithMethod `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content using the data field from the wrapper
		assert.Equal(t, len(expectedEntities), len(responseWrapper.Data))
		for i, entity := range expectedEntities {
			assert.Equal(t, entity.ID, responseWrapper.Data[i].ID)
			assert.Equal(t, entity.SettingID, responseWrapper.Data[i].SettingID)
			assert.Equal(t, entity.MethodID, responseWrapper.Data[i].MethodID)
			assert.Equal(t, entity.EntityText, responseWrapper.Data[i].EntityText)
			assert.Equal(t, entity.MethodName, responseWrapper.Data[i].MethodName)
		}

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid Method ID", func(t *testing.T) {
		// Create test request with invalid method ID
		req, err := http.NewRequest("GET", "/api/settings/entities/invalid", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create test request without auth context
		req, err := http.NewRequest("GET", "/api/settings/entities/1", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler directly to test auth check
		handler.GetModelEntities(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Create method ID
		methodID := int64(1)

		// Setup mock service to return error
		mockService.On("GetModelEntities", mock.Anything, int64(1001), methodID).
			Return(nil, errors.New("service error")).Once()

		// Create test request
		req, err := http.NewRequest("GET", "/api/settings/entities/"+strconv.FormatInt(methodID, 10), nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

func TestAddModelEntities(t *testing.T) {
	// Setup
	handler, mockService := setupSettingsTest(t)

	// Test successful case
	t.Run("Success", func(t *testing.T) {
		// Create request payload
		batch := models.ModelEntityBatch{
			MethodID:    1,
			EntityTexts: []string{"Entity 1", "Entity 2"},
		}

		// Expected created entities
		expectedEntities := []*models.ModelEntity{
			{
				ID:         1,
				SettingID:  1,
				MethodID:   batch.MethodID,
				EntityText: "Entity 1",
			},
			{
				ID:         2,
				SettingID:  1,
				MethodID:   batch.MethodID,
				EntityText: "Entity 2",
			},
		}

		// Setup mock service
		mockService.On("AddModelEntities", mock.Anything, int64(1001), mock.MatchedBy(func(b *models.ModelEntityBatch) bool {
			return b.MethodID == batch.MethodID &&
				len(b.EntityTexts) == len(batch.EntityTexts) &&
				b.EntityTexts[0] == batch.EntityTexts[0] &&
				b.EntityTexts[1] == batch.EntityTexts[1]
		})).Return(expectedEntities, nil).Once()

		// Create request body
		requestBody, err := json.Marshal(batch)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("POST", "/api/settings/entities", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.AddModelEntities(rr, req)

		// Verify response
		assert.Equal(t, http.StatusCreated, rr.Code)

		// Define wrapper for the response envelope
		var responseWrapper struct {
			Success bool                  `json:"success"`
			Data    []*models.ModelEntity `json:"data"`
		}

		// Parse response body into the wrapper
		err = json.Unmarshal(rr.Body.Bytes(), &responseWrapper)
		require.NoError(t, err)

		// Verify response content using the data field from the wrapper
		assert.Equal(t, len(expectedEntities), len(responseWrapper.Data))
		for i, entity := range expectedEntities {
			assert.Equal(t, entity.ID, responseWrapper.Data[i].ID)
			assert.Equal(t, entity.SettingID, responseWrapper.Data[i].SettingID)
			assert.Equal(t, entity.MethodID, responseWrapper.Data[i].MethodID)
			assert.Equal(t, entity.EntityText, responseWrapper.Data[i].EntityText)
		}

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid Request Body", func(t *testing.T) {
		// Create invalid JSON
		invalidJSON := []byte(`{"method_id": invalid}`)

		// Create test request
		req, err := http.NewRequest("POST", "/api/settings/entities", bytes.NewBuffer(invalidJSON))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.AddModelEntities(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create valid request body
		batch := models.ModelEntityBatch{
			MethodID:    1,
			EntityTexts: []string{"Entity 1", "Entity 2"},
		}
		requestBody, err := json.Marshal(batch)
		require.NoError(t, err)

		// Create test request without auth context
		req, err := http.NewRequest("POST", "/api/settings/entities", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.AddModelEntities(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Create request payload
		batch := models.ModelEntityBatch{
			MethodID:    1,
			EntityTexts: []string{"Entity 1", "Entity 2"},
		}

		// Setup mock service to return error
		mockService.On("AddModelEntities", mock.Anything, int64(1001), mock.MatchedBy(func(b *models.ModelEntityBatch) bool {
			return b.MethodID == batch.MethodID &&
				len(b.EntityTexts) == len(batch.EntityTexts) &&
				b.EntityTexts[0] == batch.EntityTexts[0] &&
				b.EntityTexts[1] == batch.EntityTexts[1]
		})).Return(nil, errors.New("service error")).Once()

		// Create request body
		requestBody, err := json.Marshal(batch)
		require.NoError(t, err)

		// Create test request
		req, err := http.NewRequest("POST", "/api/settings/entities", bytes.NewBuffer(requestBody))
		require.NoError(t, err)
		req.Header.Set("Content-Type", "application/json")
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler
		handler.AddModelEntities(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

func TestDeleteModelEntity(t *testing.T) {
	// Setup
	handler, mockService := setupSettingsTest(t)
	router := chi.NewRouter()
	router.Delete("/api/settings/entities/{entityID}", handler.DeleteModelEntity)

	// Test successful case
	t.Run("Success", func(t *testing.T) {
		// Create entity ID
		entityID := int64(123)

		// Setup mock service
		mockService.On("DeleteModelEntity", mock.Anything, int64(1001), entityID).Return(nil).Once()

		// Create test request
		req, err := http.NewRequest("DELETE", "/api/settings/entities/"+strconv.FormatInt(entityID, 10), nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusNoContent, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})

	t.Run("Invalid Entity ID", func(t *testing.T) {
		// Create test request with invalid entity ID
		req, err := http.NewRequest("DELETE", "/api/settings/entities/invalid", nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusBadRequest, rr.Code)
	})

	t.Run("Unauthorized", func(t *testing.T) {
		// Create test request without auth context
		req, err := http.NewRequest("DELETE", "/api/settings/entities/123", nil)
		require.NoError(t, err)

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler directly to test auth check
		handler.DeleteModelEntity(rr, req)

		// Verify response
		assert.Equal(t, http.StatusUnauthorized, rr.Code)
	})

	t.Run("Service Error", func(t *testing.T) {
		// Create entity ID
		entityID := int64(123)

		// Setup mock service to return error
		mockService.On("DeleteModelEntity", mock.Anything, int64(1001), entityID).
			Return(errors.New("service error")).Once()

		// Create test request
		req, err := http.NewRequest("DELETE", "/api/settings/entities/"+strconv.FormatInt(entityID, 10), nil)
		require.NoError(t, err)
		req = req.WithContext(createAuthContext(1001))

		// Create response recorder
		rr := httptest.NewRecorder()

		// Call the handler via router
		router.ServeHTTP(rr, req)

		// Verify response
		assert.Equal(t, http.StatusInternalServerError, rr.Code)

		// Verify mock expectations
		mockService.AssertExpectations(t)
	})
}

// Helper function to create string pointer
func stringPtr(s string) *string {
	return &s
}
