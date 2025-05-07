// Package handlers provides HTTP request handlers for the HideMe API.
package handlers

import (
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/go-chi/chi/v5"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/auth"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// GenericHandler provides handlers for generic database operations.
// It implements a REST API for CRUD operations on database tables.
//
// These handlers follow a consistent pattern and provide a flexible
// way to interact with database tables without writing custom handlers
// for each table.
type GenericHandler struct {
	dbService DatabaseServiceInterface
}

// NewGenericHandler creates a new GenericHandler with the provided database service.
//
// Parameters:
//   - dbService: Service handling database operations
//
// Returns:
//   - A properly initialized GenericHandler
func NewGenericHandler(dbService DatabaseServiceInterface) *GenericHandler {
	return &GenericHandler{
		dbService: dbService,
	}
}

// GetTableData returns all records from a table with optional filtering.
// It supports pagination via query parameters and returns the results
// in a standardized paginated format.
//
// HTTP Method:
//   - GET
//
// URL Path:
//   - /api/tables/{table}
//
// URL Parameters:
//   - table: The name of the table to query
//
// Query Parameters:
//   - page: Page number for pagination (default: 1)
//   - page_size: Number of records per page (default: 10)
//   - Any column name: Used for filtering records (e.g., ?name=John)
//
// Responses:
//   - 200 OK: Data retrieved successfully
//   - 400 Bad Request: Invalid table name or parameters
//   - 403 Forbidden: Table access not allowed
//   - 500 Internal Server Error: Server-side error
//
// @Summary Get table data
// @Description Returns all records from a table with optional filtering
// @Tags Database
// @Produce json
// @Security BearerAuth
// @Param table path string true "Table name"
// @Param page query int false "Page number (default: 1)"
// @Param page_size query int false "Records per page (default: 10)"
// @Param filter query object false "Filter parameters (column names and values)"
// @Success 200 {object} utils.Response "Data retrieved successfully with pagination"
// @Failure 400 {object} utils.Response{error=string} "Invalid table name or parameters"
// @Failure 403 {object} utils.Response{error=string} "Table access not allowed"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /db/{table} [get]
func (h *GenericHandler) GetTableData(w http.ResponseWriter, r *http.Request) {
	// Get the table name from the URL
	table := chi.URLParam(r, constants.ParamTable)
	if table == "" {
		utils.BadRequest(w, "Table name is required", nil)
		return
	}

	// Validate table access - security check to prevent access to sensitive tables
	if err := h.dbService.ValidateTableAccess(table); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Extract query parameters as conditions for filtering
	conditions := make(map[string]interface{})
	for key, values := range r.URL.Query() {
		if len(values) > 0 && key != constants.QueryParamPage && key != constants.QueryParamPageSize {
			conditions[key] = values[0]
		}
	}

	// Get pagination parameters
	paginationParams := utils.GetPaginationParams(r)

	// Get the total count for pagination
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
	utils.Paginated(w, constants.StatusOK, data, paginationParams.Page, paginationParams.PageSize, int(totalCount))
}

// GetRecordByID returns a single record from a table by its ID.
//
// HTTP Method:
//   - GET
//
// URL Path:
//   - /api/tables/{table}/{id}
//
// URL Parameters:
//   - table: The name of the table to query
//   - id: The ID of the record to retrieve
//
// Responses:
//   - 200 OK: Record retrieved successfully
//   - 400 Bad Request: Invalid table name or ID
//   - 403 Forbidden: Table access not allowed
//   - 404 Not Found: Record not found
//   - 500 Internal Server Error: Server-side error
//
// @Summary Get record by ID
// @Description Returns a single record from a table by its ID
// @Tags Database
// @Produce json
// @Security BearerAuth
// @Param table path string true "Table name"
// @Param id path string true "Record ID"
// @Success 200 {object} utils.Response{data=map[string]interface{}} "Record retrieved successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid table name or ID"
// @Failure 403 {object} utils.Response{error=string} "Table access not allowed"
// @Failure 404 {object} utils.Response{error=string} "Record not found"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /db/{table}/{id} [get]
func (h *GenericHandler) GetRecordByID(w http.ResponseWriter, r *http.Request) {
	// Get the table name and ID from the URL
	table := chi.URLParam(r, constants.ParamTable)
	idStr := chi.URLParam(r, constants.ParamID)

	if table == "" {
		utils.BadRequest(w, "Table name is required", nil)
		return
	}

	if idStr == "" {
		utils.BadRequest(w, "ID is required", nil)
		return
	}

	// Validate table access - security check to prevent access to sensitive tables
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
	utils.JSON(w, constants.StatusOK, record)
}

// CreateRecord creates a new record in a table.
//
// HTTP Method:
//   - POST
//
// URL Path:
//   - /api/tables/{table}
//
// URL Parameters:
//   - table: The name of the table to insert into
//
// Request Body:
//   - JSON object with column names and values
//
// Responses:
//   - 201 Created: Record created successfully
//   - 400 Bad Request: Invalid table name or request body
//   - 403 Forbidden: Table access not allowed
//   - 500 Internal Server Error: Server-side error
//
// @Summary Create record
// @Description Creates a new record in a table
// @Tags Database
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param table path string true "Table name"
// @Param record body object true "Record data"
// @Success 201 {object} utils.Response{data=map[string]interface{}} "Record created successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid table name or request body"
// @Failure 403 {object} utils.Response{error=string} "Table access not allowed"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /db/{table} [post]
func (h *GenericHandler) CreateRecord(w http.ResponseWriter, r *http.Request) {
	// Get the table name from the URL
	table := chi.URLParam(r, constants.ParamTable)
	if table == "" {
		utils.BadRequest(w, "Table name is required", nil)
		return
	}

	// Validate table access - security check to prevent access to sensitive tables
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

	// Prepare the parameterized query - PostgreSQL uses $1, $2, etc.
	i := 1
	for col, val := range data {
		columns = append(columns, col)
		placeholders = append(placeholders, "$"+strconv.Itoa(i))
		values = append(values, val)
		i++
	}

	// Construct the full query for PostgreSQL with RETURNING
	// RETURNING * returns the inserted row with any auto-generated values
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
	utils.JSON(w, constants.StatusCreated, result[0])
}

// UpdateRecord updates an existing record in a table.
//
// HTTP Method:
//   - PUT
//
// URL Path:
//   - /api/tables/{table}/{id}
//
// URL Parameters:
//   - table: The name of the table to update
//   - id: The ID of the record to update
//
// Request Body:
//   - JSON object with column names and values to update
//
// Responses:
//   - 200 OK: Record updated successfully
//   - 400 Bad Request: Invalid table name, ID, or request body
//   - 403 Forbidden: Table access not allowed
//   - 404 Not Found: Record not found
//   - 500 Internal Server Error: Server-side error
//
// @Summary Update record
// @Description Updates an existing record in a table
// @Tags Database
// @Accept json
// @Produce json
// @Security BearerAuth
// @Param table path string true "Table name"
// @Param id path string true "Record ID"
// @Param record body object true "Record data to update"
// @Success 200 {object} utils.Response{data=map[string]interface{}} "Record updated successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid table name, ID, or request body"
// @Failure 403 {object} utils.Response{error=string} "Table access not allowed"
// @Failure 404 {object} utils.Response{error=string} "Record not found"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /db/{table}/{id} [put]
func (h *GenericHandler) UpdateRecord(w http.ResponseWriter, r *http.Request) {
	// Get the table name and ID from the URL
	table := chi.URLParam(r, constants.ParamTable)
	idStr := chi.URLParam(r, constants.ParamID)

	if table == "" {
		utils.BadRequest(w, "Table name is required", nil)
		return
	}

	if idStr == "" {
		utils.BadRequest(w, "ID is required", nil)
		return
	}

	// Validate table access - security check to prevent access to sensitive tables
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

	// Default ID column name - handle both singular and plural table names
	idColumn := table + constants.ColumnID
	if table[len(table)-1] == 's' {
		idColumn = table[:len(table)-1] + constants.ColumnID
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

	// Prepare the parameterized query - PostgreSQL uses $1, $2, etc.
	i := 1
	for col, val := range data {
		setClauses = append(setClauses, col+" = $"+strconv.Itoa(i))
		values = append(values, val)
		i++
	}

	// Add the WHERE clause
	query += utils.JoinStrings(setClauses, ", ") + " WHERE " + idColumn + " = $" + strconv.Itoa(i)
	values = append(values, id)

	// Add RETURNING clause for PostgreSQL
	query += " RETURNING *"

	// Execute the query
	result, err := h.dbService.ExecuteQuery(r.Context(), query, values, userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	if len(result) == 0 {
		utils.NotFound(w, constants.MsgResourceNotFound)
		return
	}

	// Return the updated record
	utils.JSON(w, constants.StatusOK, result[0])
}

// DeleteRecord deletes a record from a table.
//
// HTTP Method:
//   - DELETE
//
// URL Path:
//   - /api/tables/{table}/{id}
//
// URL Parameters:
//   - table: The name of the table to delete from
//   - id: The ID of the record to delete
//
// Responses:
//   - 204 No Content: Record deleted successfully
//   - 400 Bad Request: Invalid table name or ID
//   - 403 Forbidden: Table access not allowed
//   - 404 Not Found: Record not found
//   - 500 Internal Server Error: Server-side error
//
// @Summary Delete record
// @Description Deletes a record from a table
// @Tags Database
// @Produce json
// @Security BearerAuth
// @Param table path string true "Table name"
// @Param id path string true "Record ID"
// @Success 204 {object} utils.Response "Record deleted successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid table name or ID"
// @Failure 403 {object} utils.Response{error=string} "Table access not allowed"
// @Failure 404 {object} utils.Response{error=string} "Record not found"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /db/{table}/{id} [delete]
func (h *GenericHandler) DeleteRecord(w http.ResponseWriter, r *http.Request) {
	// Get the table name and ID from the URL
	table := chi.URLParam(r, constants.ParamTable)
	idStr := chi.URLParam(r, constants.ParamID)

	if table == "" {
		utils.BadRequest(w, "Table name is required", nil)
		return
	}

	if idStr == "" {
		utils.BadRequest(w, "ID is required", nil)
		return
	}

	// Validate table access - security check to prevent access to sensitive tables
	if err := h.dbService.ValidateTableAccess(table); err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Get the user ID for auditing
	userID, _ := auth.GetUserID(r)

	// Default ID column name - handle both singular and plural table names
	idColumn := table + constants.ColumnID
	if table[len(table)-1] == 's' {
		idColumn = table[:len(table)-1] + constants.ColumnID
	}

	// Parse the ID (could be string or int depending on the table)
	var id interface{} = idStr
	if intID, err := strconv.ParseInt(idStr, 10, 64); err == nil {
		id = intID
	}

	// Execute the query - PostgreSQL uses $1, $2, etc.
	query := "DELETE FROM " + table + " WHERE " + idColumn + " = $1"

	// Execute the query
	_, err := h.dbService.ExecuteQuery(r.Context(), query, []interface{}{id}, userID)
	if err != nil {
		utils.ErrorFromAppError(w, utils.ParseError(err))
		return
	}

	// Return success - 204 No Content is appropriate for successful DELETE
	utils.NoContent(w)
}

// GetTableSchema returns the schema for a table.
// This is useful for dynamically building forms and validations.
//
// HTTP Method:
//   - GET
//
// URL Path:
//   - /api/tables/{table}/schema
//
// URL Parameters:
//   - table: The name of the table to get schema for
//
// Responses:
//   - 200 OK: Schema retrieved successfully
//   - 400 Bad Request: Invalid table name
//   - 403 Forbidden: Table access not allowed
//   - 500 Internal Server Error: Server-side error
//
// @Summary Get table schema
// @Description Returns the schema for a table
// @Tags Database
// @Produce json
// @Security BearerAuth
// @Param table path string true "Table name"
// @Success 200 {object} utils.Response{data=[]map[string]interface{}} "Schema retrieved successfully"
// @Failure 400 {object} utils.Response{error=string} "Invalid table name"
// @Failure 403 {object} utils.Response{error=string} "Table access not allowed"
// @Failure 500 {object} utils.Response{error=string} "Server error"
// @Router /db/{table}/schema [get]
func (h *GenericHandler) GetTableSchema(w http.ResponseWriter, r *http.Request) {
	// Get the table name from the URL
	table := chi.URLParam(r, constants.ParamTable)
	if table == "" {
		utils.BadRequest(w, "Table name is required", nil)
		return
	}

	// Validate table access - security check to prevent access to sensitive tables
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
	utils.JSON(w, constants.StatusOK, schema)
}
