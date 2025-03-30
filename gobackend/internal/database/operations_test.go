package database

import (
	"context"
	"database/sql"
	"reflect"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
)

// TestModel implements the Table interface for testing
type TestModel struct {
	ID        int64     `db:"test_id"`
	Name      string    `db:"name"`
	CreatedAt time.Time `db:"created_at"`
}

// TableName returns the database table name
func (m *TestModel) TableName() string {
	return "test_table"
}

func setupMockCRUD(t *testing.T) (*sql.DB, sqlmock.Sqlmock, *CRUD) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("Failed to create mock database: %v", err)
	}

	pool := &Pool{DB: db}
	crud := NewCRUD(pool)

	return db, mock, crud
}

func TestNewCRUD(t *testing.T) {

}

func TestCRUD_Create(t *testing.T) {
	db, mock, crud := setupMockCRUD(t)
	defer db.Close()

	// Create a test model
	now := time.Now()
	model := &TestModel{
		Name:      "Test Model",
		CreatedAt: now,
	}

	// Set up expectations
	mock.ExpectExec("INSERT INTO test_table").
		WithArgs("Test Model", now).
		WillReturnResult(sqlmock.NewResult(123, 1))

	// Call the Create function
	err := crud.Create(context.Background(), model)

	// Check results
	if err != nil {
		t.Errorf("Create() error = %v", err)
	}

	if model.ID != 123 {
		t.Errorf("Expected ID = %d, got %d", 123, model.ID)
	}

	// Verify that all expectations were met
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("Unfulfilled expectations: %v", err)
	}
}

func TestCRUD_GetByID(t *testing.T) {
	db, mock, crud := setupMockCRUD(t)
	defer db.Close()

	// Set up test data
	now := time.Now()
	id := int64(123)
	name := "Test Model"

	// Create the model to retrieve
	model := &TestModel{}

	// Set up expectations
	mock.ExpectQuery("SELECT (.+) FROM test_table WHERE (.+) = ?").
		WithArgs(id).
		WillReturnRows(
			sqlmock.NewRows([]string{"test_id", "name", "created_at"}).
				AddRow(id, name, now),
		)

	// Call the GetByID function
	err := crud.GetByID(context.Background(), model, id)

	// Check results
	if err != nil {
		t.Errorf("GetByID() error = %v", err)
	}

	if model.ID != id {
		t.Errorf("Expected ID = %d, got %d", id, model.ID)
	}

	if model.Name != name {
		t.Errorf("Expected Name = %s, got %s", name, model.Name)
	}

	// Verify that all expectations were met
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("Unfulfilled expectations: %v", err)
	}
}

func TestCRUD_Update(t *testing.T) {
	db, mock, crud := setupMockCRUD(t)
	defer db.Close()

	// Create a test model
	now := time.Now()
	model := &TestModel{
		ID:        123,
		Name:      "Updated Model",
		CreatedAt: now,
	}

	// Set up expectations
	mock.ExpectExec("UPDATE test_table SET (.+) WHERE (.+) = ?").
		WithArgs("Updated Model", now, 123).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Call the Update function
	err := crud.Update(context.Background(), model)

	// Check results
	if err != nil {
		t.Errorf("Update() error = %v", err)
	}

	// Verify that all expectations were met
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("Unfulfilled expectations: %v", err)
	}
}

func TestCRUD_Delete(t *testing.T) {
	db, mock, crud := setupMockCRUD(t)
	defer db.Close()

	// Set up test data
	id := int64(123)

	// Create the model for the table name
	model := &TestModel{}

	// Set up expectations
	mock.ExpectExec("DELETE FROM test_table WHERE (.+) = ?").
		WithArgs(id).
		WillReturnResult(sqlmock.NewResult(0, 1))

	// Call the Delete function
	err := crud.Delete(context.Background(), model, id)

	// Check results
	if err != nil {
		t.Errorf("Delete() error = %v", err)
	}

	// Verify that all expectations were met
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("Unfulfilled expectations: %v", err)
	}
}

func TestCRUD_List(t *testing.T) {
}

func TestCRUD_Count(t *testing.T) {
	db, mock, crud := setupMockCRUD(t)
	defer db.Close()

	// Set up test data
	conditions := map[string]interface{}{
		"name": "Test",
	}

	// Create the model for the table name
	model := &TestModel{}

	// Set up expectations
	mock.ExpectQuery("SELECT COUNT\\(\\*\\) FROM test_table WHERE (.+) = ?").
		WithArgs("Test").
		WillReturnRows(
			sqlmock.NewRows([]string{"count"}).
				AddRow(5),
		)

	// Call the Count function
	count, err := crud.Count(context.Background(), model, conditions)

	// Check results
	if err != nil {
		t.Errorf("Count() error = %v", err)
	}

	if count != 5 {
		t.Errorf("Expected count = %d, got %d", 5, count)
	}

	// Verify that all expectations were met
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Errorf("Unfulfilled expectations: %v", err)
	}
}

func TestIsZeroValue(t *testing.T) {
	tests := []struct {
		name  string
		setup func() interface{}
		want  bool
	}{
		{
			name:  "Zero int",
			setup: func() interface{} { return 0 },
			want:  true,
		},
		{
			name:  "Non-zero int",
			setup: func() interface{} { return 42 },
			want:  false,
		},
		{
			name:  "Zero string",
			setup: func() interface{} { return "" },
			want:  true,
		},
		{
			name:  "Non-zero string",
			setup: func() interface{} { return "hello" },
			want:  false,
		},
		{
			name:  "Nil pointer",
			setup: func() interface{} { var p *int = nil; return p },
			want:  true,
		},
		{
			name:  "Non-nil pointer",
			setup: func() interface{} { i := 42; return &i },
			want:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			value := tt.setup()
			result := isZeroValue(reflect.ValueOf(value))

			if result != tt.want {
				t.Errorf("isZeroValue() = %v, want %v", result, tt.want)
			}
		})
	}
}
