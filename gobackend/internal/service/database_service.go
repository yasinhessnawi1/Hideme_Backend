// Package service provides business logic implementations for the HideMe application.
// It contains services that orchestrate operations across repositories and implement
// the core application functionality.
//
// This file implements the database service, which provides controlled access to
// the database for generic operations. It includes security measures to prevent
// SQL injection and unauthorized access to sensitive tables.
package service

import (
	"context"
	"fmt"
	"strings"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/database"
	"github.com/yasinhessnawi1/Hideme_Backend/internal/utils"
)

// DatabaseService handles generic database operations for the application.
// It provides a controlled interface for performing database queries and
// operations while enforcing security measures to prevent abuse.
type DatabaseService struct {
	// db is the database connection pool
	db *database.Pool

	// crud provides generic CRUD operations
	crud *database.CRUD

	// allowedTables specifies which tables can be accessed through generic operations
	// This is a security measure to prevent access to sensitive tables
	allowedTables map[string]bool
}

// NewDatabaseService creates a new DatabaseService with the specified database connection.
// It initializes the list of tables that can be safely accessed through generic operations.
//
// Parameters:
//   - db: The database connection pool to use for operations
//
// Returns:
//   - A new DatabaseService instance with security restrictions configured
//
// The service restricts access to sensitive tables by explicitly defining
// which tables are allowed for generic operations. This is a defense-in-depth
// measure against potential SQL injection or authorization bypass attacks.
func NewDatabaseService(db *database.Pool) *DatabaseService {
	// Define allowed tables for generic operations
	allowedTables := map[string]bool{
		constants.TableDetectionMethods: true,
		// Add other tables that can be accessed generically
		// Note: Security-sensitive tables should NOT be included
	}

	return &DatabaseService{
		db:            db,
		crud:          database.NewCRUD(db),
		allowedTables: allowedTables,
	}
}

// ValidateTableAccess checks if the table is allowed for generic operations.
// This is a security measure to prevent access to sensitive tables.
//
// Parameters:
//   - table: The name of the table to check
//
// Returns:
//   - ForbiddenError if the table is not in the allowed list
//   - nil if access is permitted
//
// This method serves as a gatekeeper for all generic database operations,
// ensuring that only explicitly allowed tables can be accessed.
func (s *DatabaseService) ValidateTableAccess(table string) error {
	if !s.allowedTables[table] {
		return utils.NewForbiddenError(fmt.Sprintf("Table '%s' is not accessible through generic operations", table))
	}
	return nil
}

// ExecuteQuery executes a raw SQL query with parameters.
// This is a restricted operation with multiple security checks.
//
// Parameters:
//   - ctx: Context for the operation
//   - query: The SQL query to execute
//   - params: Parameters for the query (for prepared statement)
//   - userID: ID of the user executing the query (for auditing)
//
// Returns:
//   - The query results as a slice of map[string]interface{}
//   - ForbiddenError if the query contains disallowed patterns or isn't a SELECT
//   - Other errors for database issues
//
// Security measures implemented:
// 1. Only SELECT queries are allowed
// 2. Queries containing sensitive table names or SQL operations are rejected
// 3. All queries are logged with the requesting user's ID for audit purposes
// 4. Parameters are used in prepared statements to prevent SQL injection
func (s *DatabaseService) ExecuteQuery(ctx context.Context, query string, params []interface{}, userID int64) ([]map[string]interface{}, error) {
	// Security check: Only allow SELECT queries
	trimmedQuery := strings.TrimSpace(strings.ToUpper(query))
	if !strings.HasPrefix(trimmedQuery, "SELECT") {
		return nil, utils.NewForbiddenError("Only SELECT queries are allowed")
	}

	// Security check: No system table access
	disallowedPatterns := []string{
		constants.SchemaInformation, constants.TableUsers, constants.TableUserSettings,
		constants.TableAPIKeys, constants.TableSessions, "password", "update ", "insert ",
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

// GetTableData retrieves all records from a table with optional conditions.
//
// Parameters:
//   - ctx: Context for the operation
//   - table: The name of the table to query
//   - conditions: Optional key-value pairs to filter results (WHERE clause)
//
// Returns:
//   - The query results as a slice of map[string]interface{}
//   - ForbiddenError if the table is not allowed
//   - Other errors for database issues
//
// This method first validates table access, then constructs and executes
// a parameterized query with the specified conditions.
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
		where = append(where, fmt.Sprintf("%s = $%d", key, paramIndex))
		params = append(params, value)
		paramIndex++
	}

	if len(where) > 0 {
		query += " WHERE " + strings.Join(where, " AND ")
	}

	// Execute the query
	return s.ExecuteQuery(ctx, query, params, 0) // Pass 0 as userID since this is a system operation
}

// GetRecordByID retrieves a single record from a table by ID.
//
// Parameters:
//   - ctx: Context for the operation
//   - table: The name of the table to query
//   - id: The ID value to look up
//
// Returns:
//   - The record as a map[string]interface{}
//   - NotFoundError if no matching record exists
//   - ForbiddenError if the table is not allowed
//   - Other errors for database issues
//
// This method determines the appropriate ID column name based on the table,
// then retrieves the matching record if it exists.
func (s *DatabaseService) GetRecordByID(ctx context.Context, table string, id interface{}) (map[string]interface{}, error) {
	// Validate table access
	if err := s.ValidateTableAccess(table); err != nil {
		return nil, err
	}

	// Handle table-specific ID column names
	var idColumn string
	if table == constants.TableDetectionMethods {
		idColumn = constants.ColumnMethodID // Use correct column name for this table
	} else {
		idColumn = fmt.Sprintf("%s_id", strings.TrimSuffix(table, "s"))
	}

	// Build query
	query := fmt.Sprintf("SELECT * FROM %s WHERE %s = $1", table, idColumn)

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

// CountTableRecords counts records in a table with optional conditions.
//
// Parameters:
//   - ctx: Context for the operation
//   - table: The name of the table to count records from
//   - conditions: Optional key-value pairs to filter the count (WHERE clause)
//
// Returns:
//   - The count of matching records
//   - ForbiddenError if the table is not allowed
//   - Other errors for database issues
//
// This method constructs and executes a COUNT query with the specified conditions.
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
		where = append(where, fmt.Sprintf("%s = $%d", key, paramIndex))
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

// GetTableSchema retrieves the schema information for a table.
// This is useful for dynamic form generation and data validation.
//
// Parameters:
//   - ctx: Context for the operation
//   - table: The name of the table to get schema information for
//
// Returns:
//   - Schema information including column names, types, and constraints
//   - ForbiddenError if the table is not allowed
//   - Other errors for database issues
//
// This method queries the PostgreSQL information_schema to retrieve
// detailed metadata about the table columns.
func (s *DatabaseService) GetTableSchema(ctx context.Context, table string) ([]map[string]interface{}, error) {
	// Validate table access
	if err := s.ValidateTableAccess(table); err != nil {
		return nil, err
	}

	// Build query to get column information for PostgreSQL
	query := `
		SELECT 
			column_name, 
			data_type, 
			is_nullable,
			column_default
		FROM 
			information_schema.columns
		WHERE 
			table_name = $1
			AND table_schema = current_schema()
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
