package handlers

import (
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/service"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// SettingsHandler handles settings-related routes
type SettingsHandler struct {
	settingsService *service.SettingsService
}

// NewSettingsHandler creates a new SettingsHandler
func NewSettingsHandler(settingsService *service.SettingsService) *SettingsHandler {
	return &SettingsHandler{
		settingsService: settingsService,
	}
}

// GetSettings returns the current user's settings
func (h *SettingsHandler) GetSettings(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Get the settings
	settings, err := h.settingsService.GetUserSettings(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the settings
	utils.JSON(w, http.StatusOK, settings)
}

// UpdateSettings updates the current user's settings
func (h *SettingsHandler) UpdateSettings(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Decode and validate the request body
	var update models.UserSettingsUpdate
	if err := utils.DecodeAndValidate(r, &update); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Update the settings
	settings, err := h.settingsService.UpdateUserSettings(r.Context(), userID, &update)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the updated settings
	utils.JSON(w, http.StatusOK, settings)
}

// GetBanList returns the current user's ban list
func (h *SettingsHandler) GetBanList(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Get the ban list
	banList, err := h.settingsService.GetBanList(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the ban list
	utils.JSON(w, http.StatusOK, banList)
}

// AddBanListWords adds words to the current user's ban list
func (h *SettingsHandler) AddBanListWords(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Decode and validate the request body
	var batch models.BanListWordBatch
	if err := utils.DecodeAndValidate(r, &batch); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Add the words
	if err := h.settingsService.AddBanListWords(r.Context(), userID, batch.Words); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the updated ban list
	banList, err := h.settingsService.GetBanList(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	utils.JSON(w, http.StatusOK, banList)
}

// RemoveBanListWords removes words from the current user's ban list
func (h *SettingsHandler) RemoveBanListWords(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Decode and validate the request body
	var batch models.BanListWordBatch
	if err := utils.DecodeAndValidate(r, &batch); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Remove the words
	if err := h.settingsService.RemoveBanListWords(r.Context(), userID, batch.Words); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the updated ban list
	banList, err := h.settingsService.GetBanList(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	utils.JSON(w, http.StatusOK, banList)
}

// GetSearchPatterns returns the current user's search patterns
func (h *SettingsHandler) GetSearchPatterns(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Get the search patterns
	patterns, err := h.settingsService.GetSearchPatterns(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the search patterns
	utils.JSON(w, http.StatusOK, patterns)
}

// CreateSearchPattern creates a new search pattern for the current user
func (h *SettingsHandler) CreateSearchPattern(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Decode and validate the request body
	var pattern models.SearchPatternCreate
	if err := utils.DecodeAndValidate(r, &pattern); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Create the search pattern
	newPattern, err := h.settingsService.CreateSearchPattern(r.Context(), userID, &pattern)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the new pattern
	utils.JSON(w, http.StatusCreated, newPattern)
}

// UpdateSearchPattern updates an existing search pattern
func (h *SettingsHandler) UpdateSearchPattern(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Get the pattern ID from the URL
	patternIDStr := chi.URLParam(r, "patternID")
	patternID, err := strconv.ParseInt(patternIDStr, 10, 64)
	if err != nil {
		utils.BadRequest(w, "Invalid pattern ID", nil)
		return
	}

	// Decode and validate the request body
	var update models.SearchPatternUpdate
	if err := utils.DecodeAndValidate(r, &update); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Update the pattern
	updatedPattern, err := h.settingsService.UpdateSearchPattern(r.Context(), userID, patternID, &update)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the updated pattern
	utils.JSON(w, http.StatusOK, updatedPattern)
}

// DeleteSearchPattern deletes a search pattern
func (h *SettingsHandler) DeleteSearchPattern(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Get the pattern ID from the URL
	patternIDStr := chi.URLParam(r, "patternID")
	patternID, err := strconv.ParseInt(patternIDStr, 10, 64)
	if err != nil {
		utils.BadRequest(w, "Invalid pattern ID", nil)
		return
	}

	// Delete the pattern
	if err := h.settingsService.DeleteSearchPattern(r.Context(), userID, patternID); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return success
	utils.NoContent(w)
}

// GetModelEntities returns the model entities for a specific method
func (h *SettingsHandler) GetModelEntities(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Get the method ID from the URL
	methodIDStr := chi.URLParam(r, "methodID")
	methodID, err := strconv.ParseInt(methodIDStr, 10, 64)
	if err != nil {
		utils.BadRequest(w, "Invalid method ID", nil)
		return
	}

	// Get the entities
	entities, err := h.settingsService.GetModelEntities(r.Context(), userID, methodID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the entities
	utils.JSON(w, http.StatusOK, entities)
}

// AddModelEntities adds entities for a specific detection method
func (h *SettingsHandler) AddModelEntities(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Decode and validate the request body
	var batch models.ModelEntityBatch
	if err := utils.DecodeAndValidate(r, &batch); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Add the entities
	entities, err := h.settingsService.AddModelEntities(r.Context(), userID, &batch)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the new entities
	utils.JSON(w, http.StatusCreated, entities)
}

// DeleteModelEntity deletes a model entity
func (h *SettingsHandler) DeleteModelEntity(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, "Authentication required")
		return
	}

	// Get the entity ID from the URL
	entityIDStr := chi.URLParam(r, "entityID")
	entityID, err := strconv.ParseInt(entityIDStr, 10, 64)
	if err != nil {
		utils.BadRequest(w, "Invalid entity ID", nil)
		return
	}

	// Delete the entity
	if err := h.settingsService.DeleteModelEntity(r.Context(), userID, entityID); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return success
	utils.NoContent(w)
}
