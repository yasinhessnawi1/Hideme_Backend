package service

import (
	"context"
	"fmt"
	"strings"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// DatabaseService handles generic database operations
type DatabaseService struct {
	db   *database.Pool
	crud *database.CRUD
	// Map of allowed tables for generic operations
	allowedTables map[string]bool
}

// NewDatabaseService creates a new DatabaseService
func NewDatabaseService(db *database.Pool) *DatabaseService {
	// Define allowed tables for generic operations
	allowedTables := map[string]bool{
		"detection_methods": true,
		// Add other tables that can be accessed generically
		// Note: Security-sensitive tables should NOT be included
	}

	return &DatabaseService{
		db:            db,
		crud:          database.NewCRUD(db),
		allowedTables: allowedTables,
	}
}

// ValidateTableAccess checks if the table is allowed for generic operations
func (s *DatabaseService) ValidateTableAccess(table string) error {
	if !s.allowedTables[table] {
		return utils.NewForbiddenError(fmt.Sprintf("Table '%s' is not accessible through generic operations", table))
	}
	return nil
}

// ExecuteQuery executes a raw SQL query with parameters
// This is a restricted operation and should only be used by admin users
func (s *DatabaseService) ExecuteQuery(ctx context.Context, query string, params []interface{}, userID int64) ([]map[string]interface{}, error) {
	// Security check: Only allow SELECT queries
	trimmedQuery := strings.TrimSpace(strings.ToUpper(query))
	if !strings.HasPrefix(trimmedQuery, "SELECT") {
		return nil, utils.NewForbiddenError("Only SELECT queries are allowed")
	}

	// Security check: No system table access
	disallowedPatterns := []string{
		"information_schema", "users", "user_settings",
		"api_keys", "sessions", "password", "update ", "insert ",
		"delete ", "drop ", "alter ", "create ", "truncate "}

	for _, pattern := range disallowedPatterns {
		if strings.Contains(strings.ToLower(query), pattern) {
			log.Warn().
				Str("query", query).
				Int64("user_id", userID).
				Str("pattern", pattern).
				Msg("Potentially malicious query attempted")
			return nil, utils.NewForbiddenError("Query contains disallowed patterns")
		}
	}

	// Log the query attempt
	log.Info().
		Str("query", query).
		Interface("params", params).
		Int64("user_id", userID).
		Msg("Custom query execution requested")

	// Execute the query
	rows, err := s.db.QueryContext(ctx, query, params...)
	if err != nil {
		return nil, fmt.Errorf("query execution failed: %w", err)
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	// Get column names
	columns, err := rows.Columns()
	if err != nil {
		return nil, fmt.Errorf("failed to get column names: %w", err)
	}

	// Prepare result
	var result []map[string]interface{}

	// Iterate through rows
	for rows.Next() {
		// Create a slice of interface{} to hold the row values
		rowValues := make([]interface{}, len(columns))
		rowPointers := make([]interface{}, len(columns))
		for i := range rowValues {
			rowPointers[i] = &rowValues[i]
		}

		// Scan the row values
		if err := rows.Scan(rowPointers...); err != nil {
			return nil, fmt.Errorf("failed to scan row: %w", err)
		}

		// Create a map for the row
		rowMap := make(map[string]interface{})
		for i, colName := range columns {
			rowMap[colName] = rowValues[i]
		}

		result = append(result, rowMap)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating rows: %w", err)
	}

	return result, nil
}

// GetTableData retrieves all records from a table with optional conditions
func (s *DatabaseService) GetTableData(ctx context.Context, table string, conditions map[string]interface{}) ([]map[string]interface{}, error) {
	// Validate table access
	if err := s.ValidateTableAccess(table); err != nil {
		return nil, err
	}

	// Build query
	query := fmt.Sprintf("SELECT * FROM %s", table)
	var params []interface{}
	var where []string

	paramIndex := 1
	for key, value := range conditions {
		where = append(where, fmt.Sprintf("%s = ?", key))
		params = append(params, value)
		paramIndex++
	}

	if len(where) > 0 {
		query += " WHERE " + strings.Join(where, " AND ")
	}

	// Execute the query
	return s.ExecuteQuery(ctx, query, params, 0) // Pass 0 as userID since this is a system operation
}

// GetRecordByID retrieves a single record from a table by ID
func (s *DatabaseService) GetRecordByID(ctx context.Context, table string, id interface{}) (map[string]interface{}, error) {
	// Validate table access
	if err := s.ValidateTableAccess(table); err != nil {
		return nil, err
	}

	// TODO duw to database table mismatch when i created the tables
	// TODO in the detection_methods table have an id column called method_id
	// TODO but here is called detection_method so its just a table name mismatch
	var idColumn string
	if table == "detection_methods" {
		idColumn = "method_id" // Use correct column name for this table
	} else {
		idColumn = fmt.Sprintf("%s_id", strings.TrimSuffix(table, "s"))
	}

	// Build query
	query := fmt.Sprintf("SELECT * FROM %s WHERE %s = ?", table, idColumn)

	// Execute the query
	results, err := s.ExecuteQuery(ctx, query, []interface{}{id}, 0)
	if err != nil {
		return nil, err
	}

	if len(results) == 0 {
		return nil, utils.NewNotFoundError(table, id)
	}

	return results[0], nil
}

// CountTableRecords counts records in a table with optional conditions
func (s *DatabaseService) CountTableRecords(ctx context.Context, table string, conditions map[string]interface{}) (int64, error) {
	// Validate table access
	if err := s.ValidateTableAccess(table); err != nil {
		return 0, err
	}

	// Build query
	query := fmt.Sprintf("SELECT COUNT(*) FROM %s", table)
	var params []interface{}
	var where []string

	paramIndex := 1
	for key, value := range conditions {
		where = append(where, fmt.Sprintf("%s = ?", key))
		params = append(params, value)
		paramIndex++
	}

	if len(where) > 0 {
		query += " WHERE " + strings.Join(where, " AND ")
	}

	// Execute the query
	var count int64
	if err := s.db.QueryRowContext(ctx, query, params...).Scan(&count); err != nil {
		return 0, fmt.Errorf("failed to count records: %w", err)
	}

	return count, nil
}

// GetTableSchema retrieves the schema information for a table
func (s *DatabaseService) GetTableSchema(ctx context.Context, table string) ([]map[string]interface{}, error) {
	// Validate table access
	if err := s.ValidateTableAccess(table); err != nil {
		return nil, err
	}

	// Build query to get column information
	query := `
		SELECT 
			column_name, 
			data_type, 
			is_nullable,
			column_default
		FROM 
			information_schema.columns
		WHERE 
			table_name = ?
		ORDER BY 
			ordinal_position
	`

	// Execute the query
	results, err := s.ExecuteQuery(ctx, query, []interface{}{table}, 0)
	if err != nil {
		return nil, err
	}

	return results, nil
}
