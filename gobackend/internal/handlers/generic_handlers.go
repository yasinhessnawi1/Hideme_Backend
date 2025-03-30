package handlers

import (
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/service"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// GenericHandler handles generic database operations
type GenericHandler struct {
	dbService *service.DatabaseService
}

// NewGenericHandler creates a new GenericHandler
func NewGenericHandler(dbService *service.DatabaseService) *GenericHandler {
	return &GenericHandler{
		dbService: dbService,
	}
}

// GetTableData returns all records from a table
func (h *GenericHandler) GetTableData(w http.ResponseWriter, r *http.Request) {
	// Get the table name from the URL
	table := chi.URLParam(r, "table")
	if table == "" {
		utils.BadRequest(w, "Table name is required", nil)
		return
	}

	// Validate table access
	if err := h.dbService.ValidateTableAccess(table); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Extract query parameters as conditions
	conditions := make(map[string]interface{})
	for key, values := range r.URL.Query() {
		if len(values) > 0 && key != "page" && key != "page_size" {
			conditions[key] = values[0]
		}
	}

	// Get pagination parameters
	paginationParams := utils.GetPaginationParams(r)

	// Get the total count
	totalCount, err := h.dbService.CountTableRecords(r.Context(), table, conditions)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Get the data with pagination
	data, err := h.dbService.GetTableData(r.Context(), table, conditions)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return paginated response
	utils.Paginated(w, http.StatusOK, data, paginationParams.Page, paginationParams.PageSize, int(totalCount))
}

// GetRecordByID returns a single record by ID
func (h *GenericHandler) GetRecordByID(w http.ResponseWriter, r *http.Request) {
	// Get the table name and ID from the URL
	table := chi.URLParam(r, "table")
	idStr := chi.URLParam(r, "id")

	if table == "" {
		utils.BadRequest(w, "Table name is required", nil)
		return
	}

	if idStr == "" {
		utils.BadRequest(w, "ID is required", nil)
		return
	}

	// Validate table access
	if err := h.dbService.ValidateTableAccess(table); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Parse the ID (could be string or int depending on the table)
	var id interface{} = idStr
	if intID, err := strconv.ParseInt(idStr, 10, 64); err == nil {
		id = intID
	}

	// Get the record
	record, err := h.dbService.GetRecordByID(r.Context(), table, id)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the record
	utils.JSON(w, http.StatusOK, record)
}

// CreateRecord creates a new record in a table
func (h *GenericHandler) CreateRecord(w http.ResponseWriter, r *http.Request) {
	// Get the table name from the URL
	table := chi.URLParam(r, "table")
	if table == "" {
		utils.BadRequest(w, "Table name is required", nil)
		return
	}

	// Validate table access
	if err := h.dbService.ValidateTableAccess(table); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Decode the request body
	var data map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&data); err != nil {
		utils.BadRequest(w, "Invalid request body", nil)
		return
	}

	// Get the user ID for auditing
	userID, _ := auth.GetUserID(r)

	// Execute the query
	query := "INSERT INTO " + table + " "

	// Build the column list and values list
	if len(data) == 0 {
		utils.BadRequest(w, "No data provided", nil)
		return
	}

	var columns []string
	var placeholders []string
	var values []interface{}

	i := 1
	for col, val := range data {
		columns = append(columns, col)
		placeholders = append(placeholders, "$"+strconv.Itoa(i))
		values = append(values, val)
		i++
	}

	// Construct the full query
	query += "(" + utils.JoinStrings(columns, ", ") + ") VALUES (" + utils.JoinStrings(placeholders, ", ") + ") RETURNING *"

	// Execute the query
	result, err := h.dbService.ExecuteQuery(r.Context(), query, values, userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	if len(result) == 0 {
		utils.InternalServerError(w, utils.NewInternalServerError(nil))
		return
	}

	// Return the created record
	utils.JSON(w, http.StatusCreated, result[0])
}

// UpdateRecord updates a record in a table
func (h *GenericHandler) UpdateRecord(w http.ResponseWriter, r *http.Request) {
	// Get the table name and ID from the URL
	table := chi.URLParam(r, "table")
	idStr := chi.URLParam(r, "id")

	if table == "" {
		utils.BadRequest(w, "Table name is required", nil)
		return
	}

	if idStr == "" {
		utils.BadRequest(w, "ID is required", nil)
		return
	}

	// Validate table access
	if err := h.dbService.ValidateTableAccess(table); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Decode the request body
	var data map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&data); err != nil {
		utils.BadRequest(w, "Invalid request body", nil)
		return
	}

	// Get the user ID for auditing
	userID, _ := auth.GetUserID(r)

	// Default ID column name
	idColumn := table + "_id"
	if table[len(table)-1] == 's' {
		idColumn = table[:len(table)-1] + "_id"
	}

	// Parse the ID (could be string or int depending on the table)
	var id interface{} = idStr
	if intID, err := strconv.ParseInt(idStr, 10, 64); err == nil {
		id = intID
	}

	// Execute the query
	query := "UPDATE " + table + " SET "

	// Build the SET clause
	if len(data) == 0 {
		utils.BadRequest(w, "No data provided", nil)
		return
	}

	var setClauses []string
	var values []interface{}

	i := 1
	for col, val := range data {
		setClauses = append(setClauses, col+" = $"+strconv.Itoa(i))
		values = append(values, val)
		i++
	}

	// Add the WHERE clause
	query += utils.JoinStrings(setClauses, ", ") + " WHERE " + idColumn + " = $" + strconv.Itoa(i)
	values = append(values, id)

	// Add RETURNING clause
	query += " RETURNING *"

	// Execute the query
	result, err := h.dbService.ExecuteQuery(r.Context(), query, values, userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	if len(result) == 0 {
		utils.NotFound(w, "Record not found")
		return
	}

	// Return the updated record
	utils.JSON(w, http.StatusOK, result[0])
}

// DeleteRecord deletes a record from a table
func (h *GenericHandler) DeleteRecord(w http.ResponseWriter, r *http.Request) {
	// Get the table name and ID from the URL
	table := chi.URLParam(r, "table")
	idStr := chi.URLParam(r, "id")

	if table == "" {
		utils.BadRequest(w, "Table name is required", nil)
		return
	}

	if idStr == "" {
		utils.BadRequest(w, "ID is required", nil)
		return
	}

	// Validate table access
	if err := h.dbService.ValidateTableAccess(table); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Get the user ID for auditing
	userID, _ := auth.GetUserID(r)

	// Default ID column name
	idColumn := table + "_id"
	if table[len(table)-1] == 's' {
		idColumn = table[:len(table)-1] + "_id"
	}

	// Parse the ID (could be string or int depending on the table)
	var id interface{} = idStr
	if intID, err := strconv.ParseInt(idStr, 10, 64); err == nil {
		id = intID
	}

	// Execute the query
	query := "DELETE FROM " + table + " WHERE " + idColumn + " = $1"

	// Execute the query
	_, err := h.dbService.ExecuteQuery(r.Context(), query, []interface{}{id}, userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return success
	utils.NoContent(w)
}

// GetTableSchema returns the schema for a table
func (h *GenericHandler) GetTableSchema(w http.ResponseWriter, r *http.Request) {
	// Get the table name from the URL
	table := chi.URLParam(r, "table")
	if table == "" {
		utils.BadRequest(w, "Table name is required", nil)
		return
	}

	// Validate table access
	if err := h.dbService.ValidateTableAccess(table); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Get the schema
	schema, err := h.dbService.GetTableSchema(r.Context(), table)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return the schema
	utils.JSON(w, http.StatusOK, schema)
}
