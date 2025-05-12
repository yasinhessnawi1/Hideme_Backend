// Package database provides database access and management functions for the HideMe API.
package database

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"reflect"
	"strings"

	"github.com/rs/zerolog/log"

	"github.com/yasinhessnawi1/Hideme_Backend/internal/constants"
)

// Table represents a database table with common methods.
// This interface must be implemented by models that work with the CRUD operations.
type Table interface {
	// TableName returns the name of the database table for this model.
	TableName() string
}

// CRUD provides generic database operations for any model implementing the Table interface.
// It uses reflection to automatically handle different model structures.
type CRUD struct {
	// DB is the database connection pool
	DB *Pool
}

// NewCRUD creates a new CRUD instance with the given database pool.
//
// Parameters:
//   - db: The database connection pool to use for operations
//
// Returns:
//   - A properly initialized CRUD instance
func NewCRUD(db *Pool) *CRUD {
	return &CRUD{DB: db}
}

// Create inserts a new record into the database and sets the ID field.
// It uses reflection to determine field names and values based on struct tags.
//
// Parameters:
//   - ctx: Context for the database operation
//   - model: A pointer to a struct implementing the Table interface
//
// Returns:
//   - An error if the operation fails
func (c *CRUD) Create(ctx context.Context, model Table) error {
	// Get model type and value through reflection
	modelType := reflect.TypeOf(model).Elem()
	modelValue := reflect.ValueOf(model).Elem()

	// Extract field names and values
	var fields []string
	var placeholders []string
	var values []interface{}
	var idField reflect.Value
	var idColumn string

	// Iterate through each field in the struct
	for i := 0; i < modelType.NumField(); i++ {
		field := modelType.Field(i)
		fieldValue := modelValue.Field(i)

		// Get database column name from the "db" tag
		dbTag := field.Tag.Get("db")
		if dbTag == "" || dbTag == "-" {
			continue
		}

		// Skip zero values for auto-generated fields (like IDs)
		if strings.HasSuffix(dbTag, constants.ColumnID) && isZeroValue(fieldValue) {
			// Remember the ID field for later when we get the auto-generated ID
			idField = fieldValue
			idColumn = dbTag
			continue
		}

		// Collect field names, placeholders, and values for the SQL query
		fields = append(fields, dbTag)
		placeholders = append(placeholders, fmt.Sprintf("$%d", len(placeholders)+1)) // PostgreSQL uses $1, $2, etc.
		values = append(values, fieldValue.Interface())
	}

	// Build the SQL INSERT query
	var query string
	if idField.IsValid() {
		// For PostgreSQL, use RETURNING to get the auto-generated ID
		query = fmt.Sprintf(
			"INSERT INTO %s (%s) VALUES (%s) RETURNING %s",
			model.TableName(),
			strings.Join(fields, ", "),
			strings.Join(placeholders, ", "),
			idColumn,
		)
	} else {
		// Standard INSERT query without returning values
		query = fmt.Sprintf(
			"INSERT INTO %s (%s) VALUES (%s)",
			model.TableName(),
			strings.Join(fields, ", "),
			strings.Join(placeholders, ", "),
		)
	}

	// Log the query for debugging
	log.Debug().
		Str("query", query).
		Interface("values", values).
		Str("table", model.TableName()).
		Msg("Creating database record")

	// Execute the query
	if idField.IsValid() {
		// PostgreSQL implementation using RETURNING to get the auto-generated ID
		var id interface{}
		err := c.DB.DB.QueryRowContext(ctx, query, values...).Scan(&id)
		if err != nil {
			return fmt.Errorf("failed to create record in %s: %w", model.TableName(), err)
		}

		// Set the ID field in the model with the auto-generated ID
		idField.Set(reflect.ValueOf(id).Convert(idField.Type()))
	} else {
		// Execute the query without returning an ID
		if _, err := c.DB.DB.ExecContext(ctx, query, values...); err != nil {
			return fmt.Errorf("failed to create record in %s: %w", model.TableName(), err)
		}
	}

	return nil
}

// GetByID retrieves a record by its ID.
// It populates the provided model with the data from the database.
//
// Parameters:
//   - ctx: Context for the database operation
//   - model: A pointer to a struct implementing the Table interface
//   - id: The ID of the record to retrieve
//
// Returns:
//   - An error if the record is not found or the operation fails
func (c *CRUD) GetByID(ctx context.Context, model Table, id interface{}) error {
	// Get model type and value through reflection
	modelType := reflect.TypeOf(model).Elem()
	modelValue := reflect.ValueOf(model).Elem()

	// Extract field names for the SELECT clause
	var fields []string
	for i := 0; i < modelType.NumField(); i++ {
		field := modelType.Field(i)
		dbTag := field.Tag.Get("db")
		if dbTag == "" || dbTag == "-" {
			continue
		}
		fields = append(fields, dbTag)
	}

	// Determine ID column name
	var idColumn string
	for i := 0; i < modelType.NumField(); i++ {
		field := modelType.Field(i)
		dbTag := field.Tag.Get("db")
		if strings.HasSuffix(dbTag, constants.ColumnID) {
			idColumn = dbTag
			break
		}
	}
	if idColumn == "" {
		idColumn = constants.ColumnID // Default if not found
	}

	// Build the SQL SELECT query
	query := fmt.Sprintf(
		"SELECT %s FROM %s WHERE %s = $1",
		strings.Join(fields, ", "),
		model.TableName(),
		idColumn,
	)

	// Log the query for debugging
	log.Debug().
		Str("query", query).
		Interface("id", id).
		Str("table", model.TableName()).
		Msg("Getting database record by ID")

	// Execute the query
	row := c.DB.DB.QueryRowContext(ctx, query, id)

	// Prepare slice of pointers to receive the scanned values
	values := make([]interface{}, len(fields))
	for i := 0; i < len(fields); i++ {
		// Find the field by the database column name
		for j := 0; j < modelType.NumField(); j++ {
			field := modelType.Field(j)
			if field.Tag.Get("db") == fields[i] {
				values[i] = modelValue.Field(j).Addr().Interface()
				break
			}
		}
	}

	// Scan the result into the model
	if err := row.Scan(values...); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return fmt.Errorf("record with ID %v not found in %s", id, model.TableName())
		}
		return fmt.Errorf("failed to get record from %s: %w", model.TableName(), err)
	}

	return nil
}

// Update updates a record in the database.
// It uses reflection to determine field names and values based on struct tags.
//
// Parameters:
//   - ctx: Context for the database operation
//   - model: A pointer to a struct implementing the Table interface
//
// Returns:
//   - An error if the record is not found or the operation fails
func (c *CRUD) Update(ctx context.Context, model Table) error {
	// Get model type and value through reflection
	modelType := reflect.TypeOf(model).Elem()
	modelValue := reflect.ValueOf(model).Elem()

	// Extract field names and values
	var fields []string
	var values []interface{}
	var idValue interface{}
	var idColumn string

	paramCount := 1 // For PostgreSQL's $1, $2, etc.

	// Iterate through each field in the struct
	for i := 0; i < modelType.NumField(); i++ {
		field := modelType.Field(i)
		fieldValue := modelValue.Field(i)

		// Get database column name from the "db" tag
		dbTag := field.Tag.Get("db")
		if dbTag == "" || dbTag == "-" {
			continue
		}

		// Handle ID field separately
		if strings.HasSuffix(dbTag, constants.ColumnID) {
			idColumn = dbTag
			idValue = fieldValue.Interface()
			continue
		}

		// Collect field names and values for the SQL query
		fields = append(fields, fmt.Sprintf("%s = $%d", dbTag, paramCount))
		paramCount++
		values = append(values, fieldValue.Interface())
	}

	// Add ID as the last parameter
	values = append(values, idValue)

	// Build the SQL UPDATE query
	query := fmt.Sprintf(
		"UPDATE %s SET %s WHERE %s = $%d",
		model.TableName(),
		strings.Join(fields, ", "),
		idColumn,
		paramCount,
	)

	// Log the query for debugging
	log.Debug().
		Str("query", query).
		Interface("values", values).
		Str("table", model.TableName()).
		Msg("Updating database record")

	// Execute the query
	result, err := c.DB.DB.ExecContext(ctx, query, values...)
	if err != nil {
		return fmt.Errorf("failed to update record in %s: %w", model.TableName(), err)
	}

	// Check if any rows were affected to determine if the record exists
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("error getting rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return fmt.Errorf("record with ID %v not found in %s", idValue, model.TableName())
	}

	return nil
}

// Delete removes a record from the database.
//
// Parameters:
//   - ctx: Context for the database operation
//   - model: A struct implementing the Table interface
//   - id: The ID of the record to delete
//
// Returns:
//   - An error if the record is not found or the operation fails
func (c *CRUD) Delete(ctx context.Context, model Table, id interface{}) error {
	// Determine ID column name
	modelType := reflect.TypeOf(model).Elem()
	var idColumn string
	for i := 0; i < modelType.NumField(); i++ {
		field := modelType.Field(i)
		dbTag := field.Tag.Get("db")
		if strings.HasSuffix(dbTag, constants.ColumnID) {
			idColumn = dbTag
			break
		}
	}
	if idColumn == "" {
		idColumn = constants.ColumnID // Default if not found
	}

	// Build the SQL DELETE query
	query := fmt.Sprintf(
		"DELETE FROM %s WHERE %s = $1",
		model.TableName(),
		idColumn,
	)

	// Log the query for debugging
	log.Debug().
		Str("query", query).
		Interface("id", id).
		Str("table", model.TableName()).
		Msg("Deleting database record")

	// Execute the query
	result, err := c.DB.DB.ExecContext(ctx, query, id)
	if err != nil {
		return fmt.Errorf("failed to delete record from %s: %w", model.TableName(), err)
	}

	// Check if any rows were affected to determine if the record exists
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("error getting rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return fmt.Errorf("record with ID %v not found in %s", id, model.TableName())
	}

	return nil
}

// List retrieves all records that match the given conditions.
// It populates the provided slice with the data from the database.
//
// Parameters:
//   - ctx: Context for the database operation
//   - model: A struct implementing the Table interface
//   - dest: A pointer to a slice of the model type to populate
//   - conditions: A map of column name to value for filtering records
//
// Returns:
//   - An error if the operation fails
func (c *CRUD) List(ctx context.Context, model Table, dest interface{}, conditions map[string]interface{}) error {
	// Get type information
	destValue := reflect.ValueOf(dest).Elem()
	elemType := destValue.Type().Elem()
	if elemType.Kind() == reflect.Ptr {
		elemType = elemType.Elem()
	}

	// Extract field names for the SELECT clause
	var fields []string
	for i := 0; i < elemType.NumField(); i++ {
		field := elemType.Field(i)
		dbTag := field.Tag.Get("db")
		if dbTag == "" || dbTag == "-" {
			continue
		}
		fields = append(fields, dbTag)
	}

	// Build the SQL SELECT query
	query := fmt.Sprintf("SELECT %s FROM %s", strings.Join(fields, ", "), model.TableName())

	// Add WHERE clause if conditions are provided
	var where []string
	var params []interface{}
	paramCount := 1 // For PostgreSQL's $1, $2, etc.

	for key, value := range conditions {
		where = append(where, fmt.Sprintf("%s = $%d", key, paramCount))
		params = append(params, value)
		paramCount++
	}

	if len(where) > 0 {
		query += " WHERE " + strings.Join(where, " AND ")
	}

	// Log the query for debugging
	log.Debug().
		Str("query", query).
		Interface("params", params).
		Str("table", model.TableName()).
		Msg("Listing database records")

	// Execute the query
	rows, err := c.DB.DB.QueryContext(ctx, query, params...)
	if err != nil {
		return fmt.Errorf("failed to query records from %s: %w", model.TableName(), err)
	}
	defer func() {
		if closeErr := rows.Close(); closeErr != nil {
			log.Error().Err(closeErr).Msg("failed to close rows")
		}
	}()

	// Scan rows into the destination slice
	for rows.Next() {
		// Create a new instance of the element type
		newElem := reflect.New(elemType).Elem()

		// Prepare values for scanning
		values := make([]interface{}, len(fields))
		for i := 0; i < len(fields); i++ {
			// Find the field by the database column name
			for j := 0; j < elemType.NumField(); j++ {
				field := elemType.Field(j)
				if field.Tag.Get("db") == fields[i] {
					values[i] = newElem.Field(j).Addr().Interface()
					break
				}
			}
		}

		// Scan the row into the values
		if err := rows.Scan(values...); err != nil {
			return fmt.Errorf("failed to scan row: %w", err)
		}

		// Append the new element to the result slice
		if elemType.Kind() == reflect.Ptr {
			destValue.Set(reflect.Append(destValue, newElem.Addr()))
		} else {
			destValue.Set(reflect.Append(destValue, newElem))
		}
	}

	// Check for errors from iterating over rows
	if err := rows.Err(); err != nil {
		return fmt.Errorf("error iterating rows: %w", err)
	}

	return nil
}

// Count gets the count of records in a table with optional conditions.
//
// Parameters:
//   - ctx: Context for the database operation
//   - model: A struct implementing the Table interface
//   - conditions: A map of column name to value for filtering records
//
// Returns:
//   - The count of matching records
//   - An error if the operation fails
func (c *CRUD) Count(ctx context.Context, model Table, conditions map[string]interface{}) (int64, error) {
	// Build the SQL COUNT query
	query := fmt.Sprintf("SELECT COUNT(*) FROM %s", model.TableName())

	// Add WHERE clause if conditions are provided
	var where []string
	var params []interface{}
	paramCount := 1 // For PostgreSQL's $1, $2, etc.

	for key, value := range conditions {
		where = append(where, fmt.Sprintf("%s = $%d", key, paramCount))
		params = append(params, value)
		paramCount++
	}

	if len(where) > 0 {
		query += " WHERE " + strings.Join(where, " AND ")
	}

	// Log the query for debugging
	log.Debug().
		Str("query", query).
		Interface("params", params).
		Str("table", model.TableName()).
		Msg("Counting database records")

	// Execute the query
	var count int64
	if err := c.DB.DB.QueryRowContext(ctx, query, params...).Scan(&count); err != nil {
		return 0, fmt.Errorf("failed to count records in %s: %w", model.TableName(), err)
	}

	return count, nil
}

// isZeroValue is a helper function to check if a value is the zero value for its type.
// This is used to detect auto-increment ID fields that should be skipped in INSERT queries.
//
// Parameters:
//   - v: The reflect.Value to check
//
// Returns:
//   - true if the value is the zero value for its type, false otherwise
func isZeroValue(v reflect.Value) bool {
	switch v.Kind() {
	case reflect.Bool:
		return !v.Bool()
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		return v.Int() == 0
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64, reflect.Uintptr:
		return v.Uint() == 0
	case reflect.Float32, reflect.Float64:
		return v.Float() == 0
	case reflect.Complex64, reflect.Complex128:
		return v.Complex() == 0
	case reflect.String:
		return v.String() == ""
	case reflect.Interface, reflect.Ptr:
		return v.IsNil()
	}
	return false
}
