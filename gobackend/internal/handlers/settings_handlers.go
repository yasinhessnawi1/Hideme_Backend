// Package handlers provides HTTP request handlers for the HideMe API.
package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/models"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// SettingsHandler handles HTTP requests related to user settings.
// It provides endpoints for managing user preferences, ban lists,
// search patterns, and model entities.
type SettingsHandler struct {
	settingsService SettingsServiceInterface
}

// NewSettingsHandler creates a new SettingsHandler with the provided settings service.
//
// Parameters:
//   - settingsService: Service handling settings operations
//
// Returns:
//   - A properly initialized SettingsHandler
func NewSettingsHandler(settingsService SettingsServiceInterface) *SettingsHandler {
	return &SettingsHandler{
		settingsService: settingsService,
	}
}

// GetSettings returns the current user's settings.
//
// HTTP Method:
//   - GET
//
// URL Path:
//   - /api/settings
//
// Requires:
//   - Authentication: User must be logged in
//
// Responses:
//   - 200 OK: Settings retrieved successfully
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// @Summary Get user settings
// @Description Returns the current user's settings
// @Tags Settings
// @Produce json
// @Security BearerAuth
// @Success 200 {object} utils.Response{data=models.UserSetting} "Settings retrieved successfully"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings [get]
func (h *SettingsHandler) GetSettings(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the settings
	settings, err := h.settingsService.GetUserSettings(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the settings
	utils.JSON(w, constants.StatusOK, settings)
}

// UpdateSettings updates the current user's settings.
//
// HTTP Method:
//   - PUT
//
// URL Path:
//   - /api/settings
//
// Requires:
//   - Authentication: User must be logged in
//
// Request Body:
//   - JSON object with settings to update
//
// Responses:
//   - 200 OK: Settings updated successfully
//   - 400 Bad Request: Invalid request body
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// @Summary Update user settings
// @Description Updates the current user's settings
// @Tags Settings
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param settings body models.UserSettingsUpdate true "Settings to update"
// @Success 200 {object} utils.Response{data=models.UserSetting} "Settings updated successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid request body"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings [put]
func (h *SettingsHandler) UpdateSettings(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
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
	utils.JSON(w, constants.StatusOK, settings)
}

// GetBanList returns the current user's ban list.
//
// HTTP Method:
//   - GET
//
// URL Path:
//   - /api/settings/ban-list
//
// Requires:
//   - Authentication: User must be logged in
//
// Responses:
//   - 200 OK: Ban list retrieved successfully
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// @Summary Get ban list
// @Description Returns the current user's ban list
// @Tags Settings/Ban List
// @Produce json
// @Security BearerAuth
// @Success 200 {object} utils.Response{data=models.BanListWithWords} "Ban list retrieved successfully"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/ban-list [get]
func (h *SettingsHandler) GetBanList(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the ban list
	banList, err := h.settingsService.GetBanList(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the ban list
	utils.JSON(w, constants.StatusOK, banList)
}

// AddBanListWords adds words to the current user's ban list.
//
// HTTP Method:
//   - POST
//
// URL Path:
//   - /api/settings/ban-list/words
//
// Requires:
//   - Authentication: User must be logged in
//
// Request Body:
//   - JSON object with "words" array of strings
//
// Responses:
//   - 200 OK: Words added successfully
//   - 400 Bad Request: Invalid request body
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// @Summary Add ban list words
// @Description Adds words to the current user's ban list
// @Tags Settings/Ban List
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param words body models.BanListWordBatch true "Words to add to ban list"
// @Success 200 {object} utils.Response{data=models.BanListWithWords} "Words added successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid request body"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/ban-list/words [post]
func (h *SettingsHandler) AddBanListWords(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
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

	utils.JSON(w, constants.StatusOK, banList)
}

// RemoveBanListWords removes words from the current user's ban list.
//
// HTTP Method:
//   - DELETE
//
// URL Path:
//   - /api/settings/ban-list/words
//
// Requires:
//   - Authentication: User must be logged in
//
// Request Body:
//   - JSON object with "words" array of strings
//
// Responses:
//   - 200 OK: Words removed successfully
//   - 400 Bad Request: Invalid request body
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// @Summary Remove ban list words
// @Description Removes words from the current user's ban list
// @Tags Settings/Ban List
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param words body models.BanListWordBatch true "Words to remove from ban list"
// @Success 200 {object} utils.Response{data=models.BanListWithWords} "Words removed successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid request body"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/ban-list/words [delete]
func (h *SettingsHandler) RemoveBanListWords(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
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

	utils.JSON(w, constants.StatusOK, banList)
}

// GetSearchPatterns returns the current user's search patterns.
//
// HTTP Method:
//   - GET
//
// URL Path:
//   - /api/settings/search-patterns
//
// Requires:
//   - Authentication: User must be logged in
//
// Responses:
//   - 200 OK: Search patterns retrieved successfully
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// @Summary Get search patterns
// @Description Returns the current user's search patterns
// @Tags Settings/Patterns
// @Produce json
// @Security BearerAuth
// @Success 200 {object} utils.Response{data=[]models.SearchPattern} "Search patterns retrieved successfully"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/patterns [get]
func (h *SettingsHandler) GetSearchPatterns(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the search patterns
	patterns, err := h.settingsService.GetSearchPatterns(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the search patterns
	utils.JSON(w, constants.StatusOK, patterns)
}

// CreateSearchPattern creates a new search pattern for the current user.
//
// HTTP Method:
//   - POST
//
// URL Path:
//   - /api/settings/search-patterns
//
// Requires:
//   - Authentication: User must be logged in
//
// Request Body:
//   - JSON object conforming to models.SearchPatternCreate
//
// Responses:
//   - 201 Created: Search pattern created successfully
//   - 400 Bad Request: Invalid request body
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// @Summary Create search pattern
// @Description Creates a new search pattern for the current user
// @Tags Settings/Patterns
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param pattern body models.SearchPatternCreate true "Search pattern to create"
// @Success 201 {object} utils.Response{data=models.SearchPattern} "Search pattern created successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid request body"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/patterns [post]
func (h *SettingsHandler) CreateSearchPattern(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
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
	utils.JSON(w, constants.StatusCreated, newPattern)
}

// UpdateSearchPattern updates an existing search pattern.
//
// HTTP Method:
//   - PUT
//
// URL Path:
//   - /api/settings/search-patterns/{pattern_id}
//
// URL Parameters:
//   - pattern_id: The ID of the search pattern to update
//
// Requires:
//   - Authentication: User must be logged in
//
// Request Body:
//   - JSON object conforming to models.SearchPatternUpdate
//
// Responses:
//   - 200 OK: Search pattern updated successfully
//   - 400 Bad Request: Invalid request body or pattern ID
//   - 401 Unauthorized: User not authenticated
//   - 404 Not Found: Pattern not found
//   - 500 Internal Server Error: Server-side error
//
// @Summary Update search pattern
// @Description Updates an existing search pattern
// @Tags Settings/Patterns
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param patternID path int true "ID of the pattern to update"
// @Param pattern body models.SearchPatternUpdate true "Search pattern updates"
// @Success 200 {object} utils.Response{data=models.SearchPattern} "Search pattern updated successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid request body or pattern ID"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 404 {object} utils.Response{error=string} "Pattern not found"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/patterns/{patternID} [put]
func (h *SettingsHandler) UpdateSearchPattern(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the pattern ID from the URL
	patternIDStr := chi.URLParam(r, constants.ParamPatternID)
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
	utils.JSON(w, constants.StatusOK, updatedPattern)
}

// DeleteSearchPattern deletes a search pattern.
//
// HTTP Method:
//   - DELETE
//
// URL Path:
//   - /api/settings/search-patterns/{pattern_id}
//
// URL Parameters:
//   - pattern_id: The ID of the search pattern to delete
//
// Requires:
//   - Authentication: User must be logged in
//
// Responses:
//   - 204 No Content: Search pattern deleted successfully
//   - 400 Bad Request: Invalid pattern ID
//   - 401 Unauthorized: User not authenticated
//   - 404 Not Found: Pattern not found
//   - 500 Internal Server Error: Server-side error
//
// @Summary Delete search pattern
// @Description Deletes a search pattern
// @Tags Settings/Patterns
// @Produce json
// @Security BearerAuth
// @Param patternID path int true "ID of the pattern to delete"
// @Success 204 {object} utils.Response "Search pattern deleted successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid pattern ID"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 404 {object} utils.Response{error=string} "Pattern not found"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/patterns/{patternID} [delete]
func (h *SettingsHandler) DeleteSearchPattern(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the pattern ID from the URL
	patternIDStr := chi.URLParam(r, constants.ParamPatternID)
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

// GetModelEntities returns the model entities for a specific method.
//
// HTTP Method:
//   - GET
//
// URL Path:
//   - /api/settings/methods/{method_id}/entities
//
// URL Parameters:
//   - method_id: The ID of the method to get entities for
//
// Requires:
//   - Authentication: User must be logged in
//
// Responses:
//   - 200 OK: Entities retrieved successfully
//   - 400 Bad Request: Invalid method ID
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// @Summary Get model entities
// @Description Returns the model entities for a specific method
// @Tags Settings/Entities
// @Produce json
// @Security BearerAuth
// @Param methodID path int true "ID of the method to get entities for"
// @Success 200 {object} utils.Response{data=[]models.ModelEntityWithMethod} "Entities retrieved successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid method ID"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/entities/{methodID} [get]
func (h *SettingsHandler) GetModelEntities(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the method ID from the URL
	methodIDStr := chi.URLParam(r, constants.ParamMethodID)
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
	utils.JSON(w, constants.StatusOK, entities)
}

// AddModelEntities adds entities for a specific detection method.
//
// HTTP Method:
//   - POST
//
// URL Path:
//   - /api/settings/methods/entities
//
// Requires:
//   - Authentication: User must be logged in
//
// Request Body:
//   - JSON object conforming to models.ModelEntityBatch
//
// Responses:
//   - 201 Created: Entities added successfully
//   - 400 Bad Request: Invalid request body
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// @Summary Add model entities
// @Description Adds entities for a specific detection method
// @Tags Settings/Entities
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param batch body models.ModelEntityBatch true "Batch of entities to add"
// @Success 201 {object} utils.Response{data=[]models.ModelEntity} "Entities added successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid request body"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/entities [post]
func (h *SettingsHandler) AddModelEntities(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
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
	utils.JSON(w, constants.StatusCreated, entities)
}

// DeleteModelEntity deletes a model entity.
//
// HTTP Method:
//   - DELETE
//
// URL Path:
//   - /api/settings/methods/entities/{entity_id}
//
// URL Parameters:
//   - entity_id: The ID of the entity to delete
//
// Requires:
//   - Authentication: User must be logged in
//
// Responses:
//   - 204 No Content: Entity deleted successfully
//   - 400 Bad Request: Invalid entity ID
//   - 401 Unauthorized: User not authenticated
//   - 404 Not Found: Entity not found
//   - 500 Internal Server Error: Server-side error
//
// @Summary Delete model entity
// @Description Deletes a model entity
// @Tags Settings/Entities
// @Produce json
// @Security BearerAuth
// @Param entityID path int true "ID of the entity to delete"
// @Success 204 {object} utils.Response "Entity deleted successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid entity ID"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 404 {object} utils.Response{error=string} "Entity not found"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/entities/{entityID} [delete]
func (h *SettingsHandler) DeleteModelEntity(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the entity ID from the URL
	entityIDStr := chi.URLParam(r, constants.ParamEntityID)
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

// DeleteModelEntityByMethodID deletes model entities by method ID.
//
// HTTP Method:
//   - DELETE
//
// URL Path:
//   - /api/settings/methods/{method_id}/entities
//
// URL Parameters:
//   - method_id: The ID of the method to delete entities for
//
// Requires:
//   - Authentication: User must be logged in
//
// Responses:
//   - 204 No Content: Entities deleted successfully
//   - 400 Bad Request: Invalid method ID
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// @Summary Delete model entities by method
// @Description Deletes all model entities for a specific method
// @Tags Settings/Entities
// @Produce json
// @Security BearerAuth
// @Param methodID path int true "ID of the method to delete entities for"
// @Success 204 {object} utils.Response "Entities deleted successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid method ID"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/entities/delete_entities_by_method_id/{methodID} [delete]
func (h *SettingsHandler) DeleteModelEntityByMethodID(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the entity ID from the URL
	methodIDStr := chi.URLParam(r, constants.ParamMethodID)
	methodID, err := strconv.ParseInt(methodIDStr, 10, 64)
	if err != nil {
		utils.BadRequest(w, "Invalid entity ID", nil)
		return
	}

	// Delete the entity
	if err := h.settingsService.DeleteModelEntityByMethodID(r.Context(), userID, methodID); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return success
	utils.NoContent(w)
}

// ExportSettings exports all user settings as a JSON file.
// This allows users to backup their settings or transfer them to another account.
//
// HTTP Method:
//   - GET
//
// URL Path:
//   - /api/settings/export
//
// Requires:
//   - Authentication: User must be logged in
//
// Responses:
//   - 200 OK: Settings exported successfully as a downloadable JSON file
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// @Summary Export settings
// @Description Exports all user settings as a JSON file
// @Tags Settings
// @Produce json
// @Security BearerAuth
// @Success 200 {file} byte[] "Settings exported successfully as a downloadable JSON file"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/export [get]
func (h *SettingsHandler) ExportSettings(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Get the complete settings export from the service
	settingsExport, err := h.settingsService.ExportSettings(r.Context(), userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Get the username for the filename
	username, usernameOk := auth.GetUsername(r)

	// Generate meaningful filename with username
	var filename string
	if usernameOk && username != "" {
		// Remove any spaces or special characters from username for a safe filename
		safeUsername := strings.Map(func(r rune) rune {
			if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '_' {
				return r
			}
			return '_'
		}, username)

		filename = fmt.Sprintf("%s_settings.json", safeUsername)
	} else {
		filename = fmt.Sprintf("user_%d_settings.json", userID)
	}

	// Use the JsonFile method to send as downloadable file
	utils.JsonFile(w, settingsExport, filename)
}

// ImportSettings imports user settings from a JSON file.
// This allows users to restore previously exported settings.
//
// HTTP Method:
//   - POST
//
// URL Path:
//   - /api/settings/import
//
// Requires:
//   - Authentication: User must be logged in
//   - Content-Type: multipart/form-data
//   - Form field: "settings" - JSON file with settings to import
//
// Responses:
//   - 200 OK: Settings imported successfully
//   - 400 Bad Request: Invalid file format or content
//   - 401 Unauthorized: User not authenticated
//   - 500 Internal Server Error: Server-side error
//
// Security:
//   - The file size is limited to prevent denial of service attacks
//   - The file type is validated to ensure only JSON files are accepted
//   - The imported settings are validated before being applied
//
// @Summary Import settings
// @Description Imports user settings from a JSON file
// @Tags Settings
// @Accept multipart/form-data
// @Produce json
// @Security BearerAuth
// @Param settings formData file true "JSON file with settings to import"
// @Success 200 {object} utils.Response{data=map[string]string} "Settings imported successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid file format or content"
// @Failure 401 {object} utils.Response{error=string} "User not authenticated"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /settings/import [post]
func (h *SettingsHandler) ImportSettings(w http.ResponseWriter, r *http.Request) {
	// Get the user ID from the context
	userID, ok := auth.GetUserID(r)
	if !ok {
		utils.Unauthorized(w, constants.MsgAuthRequired)
		return
	}

	// Limit the size of the upload to prevent denial of service attacks
	maxSize := int64(constants.MaxRequestBodySize)
	r.Body = http.MaxBytesReader(w, r.Body, maxSize)

	// Parse the multipart form file
	if err := r.ParseMultipartForm(maxSize); err != nil {
		utils.BadRequest(w, "Invalid file upload: "+err.Error(), nil)
		return
	}

	// Get the file from the form
	file, header, err := r.FormFile("settings")
	if err != nil {
		utils.BadRequest(w, "Settings file is required", nil)
		return
	}
	defer file.Close()

	// Validate file type to ensure only JSON files are accepted
	if !strings.HasSuffix(strings.ToLower(header.Filename), ".json") {
		utils.BadRequest(w, "Only JSON files are allowed", nil)
		return
	}

	// Read and parse the settings JSON
	var settingsExport models.SettingsExport
	decoder := json.NewDecoder(file)
	if err := decoder.Decode(&settingsExport); err != nil {
		utils.BadRequest(w, "Invalid JSON format: "+err.Error(), nil)
		return
	}

	// Validate the import data
	if settingsExport.GeneralSettings == nil {
		utils.BadRequest(w, "Missing general settings in import file", nil)
		return
	}

	// Validate theme value if present
	if theme := settingsExport.GeneralSettings.Theme; theme != "" &&
		theme != constants.ThemeSystem &&
		theme != constants.ThemeLight &&
		theme != constants.ThemeDark {
		utils.BadRequest(w, "Invalid theme value", nil)
		return
	}

	// Import settings
	if err := h.settingsService.ImportSettings(r.Context(), userID, &settingsExport); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return success
	utils.JSON(w, constants.StatusOK, map[string]interface{}{
		"message": constants.MsgSettingsImported,
	})
}
