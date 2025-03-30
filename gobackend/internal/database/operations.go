package database

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"reflect"
	"strings"

	"github.com/rs/zerolog/log"
)

// Table represents a database table with common methods
type Table interface {
	TableName() string
}

// CRUD provides generic database operations for any model
type CRUD struct {
	DB *Pool
}

// NewCRUD creates a new CRUD instance with the given database pool
func NewCRUD(db *Pool) *CRUD {
	return &CRUD{DB: db}
}

// Create inserts a new record into the database and sets the ID field
func (c *CRUD) Create(ctx context.Context, model Table) error {
	// Get model type and value
	modelType := reflect.TypeOf(model).Elem()
	modelValue := reflect.ValueOf(model).Elem()

	// Extract field names and values
	var fields []string
	var placeholders []string
	var values []interface{}
	var idField reflect.Value

	for i := 0; i < modelType.NumField(); i++ {
		field := modelType.Field(i)
		fieldValue := modelValue.Field(i)

		// Get database column name from tag
		dbTag := field.Tag.Get("db")
		if dbTag == "" || dbTag == "-" {
			continue
		}

		// Skip zero values for auto-generated fields (like IDs)
		if strings.HasSuffix(dbTag, "_id") && isZeroValue(fieldValue) {
			// Remember the ID field for later
			idField = fieldValue
			continue
		}

		fields = append(fields, dbTag)
		placeholders = append(placeholders, "?") // MySQL uses ? for placeholders
		values = append(values, fieldValue.Interface())
	}

	// Build the query
	query := fmt.Sprintf(
		"INSERT INTO %s (%s) VALUES (%s)",
		model.TableName(),
		strings.Join(fields, ", "),
		strings.Join(placeholders, ", "),
	)

	// Log the query
	log.Debug().
		Str("query", query).
		Interface("values", values).
		Str("table", model.TableName()).
		Msg("Creating database record")

	// Execute the query
	if idField.IsValid() {
		// MySQL implementation using LastInsertId
		result, err := c.DB.ExecContext(ctx, query, values...)
		if err != nil {
			return fmt.Errorf("failed to create record in %s: %w", model.TableName(), err)
		}

		// Get the last inserted ID
		lastID, err := result.LastInsertId()
		if err != nil {
			return fmt.Errorf("failed to get last insert ID: %w", err)
		}

		// Set the ID field in the model
		idField.Set(reflect.ValueOf(lastID).Convert(idField.Type()))
	} else {
		if _, err := c.DB.ExecContext(ctx, query, values...); err != nil {
			return fmt.Errorf("failed to create record in %s: %w", model.TableName(), err)
		}
	}

	return nil
}

// GetByID retrieves a record by its ID
func (c *CRUD) GetByID(ctx context.Context, model Table, id interface{}) error {
	// Get model type and value
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
		if strings.HasSuffix(dbTag, "_id") {
			idColumn = dbTag
			break
		}
	}
	if idColumn == "" {
		idColumn = "id" // Default if not found
	}

	// Build the query
	query := fmt.Sprintf(
		"SELECT %s FROM %s WHERE %s = ?",
		strings.Join(fields, ", "),
		model.TableName(),
		idColumn,
	)

	// Log the query
	log.Debug().
		Str("query", query).
		Interface("id", id).
		Str("table", model.TableName()).
		Msg("Getting database record by ID")

	// Execute the query
	row := c.DB.QueryRowContext(ctx, query, id)

	// Scan the result into the model
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

	if err := row.Scan(values...); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return fmt.Errorf("record with ID %v not found in %s", id, model.TableName())
		}
		return fmt.Errorf("failed to get record from %s: %w", model.TableName(), err)
	}

	return nil
}

// Update updates a record in the database
func (c *CRUD) Update(ctx context.Context, model Table) error {
	// Get model type and value
	modelType := reflect.TypeOf(model).Elem()
	modelValue := reflect.ValueOf(model).Elem()

	// Extract field names and values
	var fields []string
	var values []interface{}
	var idValue interface{}
	var idColumn string

	for i := 0; i < modelType.NumField(); i++ {
		field := modelType.Field(i)
		fieldValue := modelValue.Field(i)

		// Get database column name from tag
		dbTag := field.Tag.Get("db")
		if dbTag == "" || dbTag == "-" {
			continue
		}

		// Handle ID field separately
		if strings.HasSuffix(dbTag, "_id") {
			idColumn = dbTag
			idValue = fieldValue.Interface()
			continue
		}

		fields = append(fields, fmt.Sprintf("%s = ?", dbTag))
		values = append(values, fieldValue.Interface())
	}

	// Add ID as the last parameter
	values = append(values, idValue)

	// Build the query
	query := fmt.Sprintf(
		"UPDATE %s SET %s WHERE %s = ?",
		model.TableName(),
		strings.Join(fields, ", "),
		idColumn,
	)

	// Log the query
	log.Debug().
		Str("query", query).
		Interface("values", values).
		Str("table", model.TableName()).
		Msg("Updating database record")

	// Execute the query
	result, err := c.DB.ExecContext(ctx, query, values...)
	if err != nil {
		return fmt.Errorf("failed to update record in %s: %w", model.TableName(), err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("error getting rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return fmt.Errorf("record with ID %v not found in %s", idValue, model.TableName())
	}

	return nil
}

// Delete removes a record from the database
func (c *CRUD) Delete(ctx context.Context, model Table, id interface{}) error {
	// Determine ID column name
	modelType := reflect.TypeOf(model).Elem()
	var idColumn string
	for i := 0; i < modelType.NumField(); i++ {
		field := modelType.Field(i)
		dbTag := field.Tag.Get("db")
		if strings.HasSuffix(dbTag, "_id") {
			idColumn = dbTag
			break
		}
	}
	if idColumn == "" {
		idColumn = "id" // Default if not found
	}

	// Build the query
	query := fmt.Sprintf(
		"DELETE FROM %s WHERE %s = ?",
		model.TableName(),
		idColumn,
	)

	// Log the query
	log.Debug().
		Str("query", query).
		Interface("id", id).
		Str("table", model.TableName()).
		Msg("Deleting database record")

	// Execute the query
	result, err := c.DB.ExecContext(ctx, query, id)
	if err != nil {
		return fmt.Errorf("failed to delete record from %s: %w", model.TableName(), err)
	}

	// Check if any rows were affected
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("error getting rows affected: %w", err)
	}

	if rowsAffected == 0 {
		return fmt.Errorf("record with ID %v not found in %s", id, model.TableName())
	}

	return nil
}

// List retrieves all records that match the given conditions
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

	// Build query
	query := fmt.Sprintf("SELECT %s FROM %s", strings.Join(fields, ", "), model.TableName())

	// Add WHERE clause if conditions are provided
	var where []string
	var params []interface{}

	for key, value := range conditions {
		where = append(where, fmt.Sprintf("%s = ?", key))
		params = append(params, value)
	}

	if len(where) > 0 {
		query += " WHERE " + strings.Join(where, " AND ")
	}

	// Log the query
	log.Debug().
		Str("query", query).
		Interface("params", params).
		Str("table", model.TableName()).
		Msg("Listing database records")

	// Execute the query
	rows, err := c.DB.QueryContext(ctx, query, params...)
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

	if err := rows.Err(); err != nil {
		return fmt.Errorf("error iterating rows: %w", err)
	}

	return nil
}

// Count gets the count of records in a table with optional conditions
func (c *CRUD) Count(ctx context.Context, model Table, conditions map[string]interface{}) (int64, error) {
	// Build query
	query := fmt.Sprintf("SELECT COUNT(*) FROM %s", model.TableName())

	// Add WHERE clause if conditions are provided
	var where []string
	var params []interface{}

	for key, value := range conditions {
		where = append(where, fmt.Sprintf("%s = ?", key))
		params = append(params, value)
	}

	if len(where) > 0 {
		query += " WHERE " + strings.Join(where, " AND ")
	}

	// Log the query
	log.Debug().
		Str("query", query).
		Interface("params", params).
		Str("table", model.TableName()).
		Msg("Counting database records")

	// Execute the query
	var count int64
	if err := c.DB.QueryRowContext(ctx, query, params...).Scan(&count); err != nil {
		return 0, fmt.Errorf("failed to count records in %s: %w", model.TableName(), err)
	}

	return count, nil
}

// Helper function to check if a value is the zero value for its type
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
