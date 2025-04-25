// Package handlers provides HTTP request handlers for the HideMe API.
package handlers

import (
	"context"
)

// DatabaseServiceInterface defines methods required from the database service.
// This interface is used by the generic handlers to interact with the database
// without being tightly coupled to the implementation.
//
// It provides methods for secure and controlled access to database operations,
// including validation of table access permissions and query execution.
type DatabaseServiceInterface interface {
	// ValidateTableAccess checks if a table is accessible to the API.
	// This is a security measure to prevent access to sensitive tables.
	//
	// Parameters:
	//   - table: The name of the table to validate
	//
	// Returns:
	//   - An error if the table is not accessible or doesn't exist
	ValidateTableAccess(table string) error

	// ExecuteQuery executes a SQL query with parameters and returns the results.
	// The userID is included for auditing and access control purposes.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - query: The SQL query to execute
	//   - params: Query parameters for prepared statements
	//   - userID: The ID of the user executing the query (for auditing)
	//
	// Returns:
	//   - The query results as a slice of map[string]interface{}
	//   - An error if the query execution fails
	ExecuteQuery(ctx context.Context, query string, params []interface{}, userID int64) ([]map[string]interface{}, error)

	// GetTableData retrieves records from a table with optional filtering.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - table: The name of the table to query
	//   - conditions: Map of column name to value for WHERE conditions
	//
	// Returns:
	//   - The matching records as a slice of map[string]interface{}
	//   - An error if the data retrieval fails
	GetTableData(ctx context.Context, table string, conditions map[string]interface{}) ([]map[string]interface{}, error)

	// GetRecordByID retrieves a single record by its ID.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - table: The name of the table to query
	//   - id: The ID of the record to retrieve
	//
	// Returns:
	//   - The matching record as map[string]interface{}
	//   - An error if the record is not found or retrieval fails
	GetRecordByID(ctx context.Context, table string, id interface{}) (map[string]interface{}, error)

	// CountTableRecords counts the number of records in a table with optional filtering.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - table: The name of the table to count records from
	//   - conditions: Map of column name to value for WHERE conditions
	//
	// Returns:
	//   - The count of matching records
	//   - An error if the counting operation fails
	CountTableRecords(ctx context.Context, table string, conditions map[string]interface{}) (int64, error)

	// GetTableSchema returns the schema information for a table.
	//
	// Parameters:
	//   - ctx: Context for the operation
	//   - table: The name of the table to get schema for
	//
	// Returns:
	//   - The table schema as a slice of map[string]interface{}
	//     containing column names, types, constraints, etc.
	//   - An error if the schema retrieval fails
	GetTableSchema(ctx context.Context, table string) ([]map[string]interface{}, error)
}
