package migrations

import (
	"context"
	"database/sql"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/stretchr/testify/assert"
)

// createMockDB creates a mock database for testing
func createMockDBAndTx(t *testing.T) (*sql.DB, *sql.Tx, sqlmock.Sqlmock, func()) {
	db, mock, err := sqlmock.New()
	if err != nil {
		t.Fatalf("Failed to create mock database: %v", err)
	}

	mock.ExpectBegin()
	tx, err := db.Begin()
	if err != nil {
		t.Fatalf("Failed to create transaction: %v", err)
	}

	cleanup := func() {
		tx.Rollback()
		db.Close()
	}

	return db, tx, mock, cleanup
}

// Test individual table creation functions
func TestCreateUsersTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createUsersTable()

	assert.Equal(t, "create_users_table", migration.Name)
	assert.Equal(t, "Creates the users table", migration.Description)
	assert.Equal(t, "users", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Expect the SQL execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS users").
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Test the SQL execution
	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestCreateUserSettingsTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createUserSettingsTable()

	assert.Equal(t, "create_user_settings_table", migration.Name)
	assert.Equal(t, "Creates the user_settings table", migration.Description)
	assert.Equal(t, "user_settings", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Expect the SQL execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS user_settings").
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Test the SQL execution
	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestCreateDocumentsTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createDocumentsTable()

	assert.Equal(t, "create_documents_table", migration.Name)
	assert.Equal(t, "Creates the documents table", migration.Description)
	assert.Equal(t, "documents", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Expect the SQL execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS documents").
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Test the SQL execution
	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestCreateDetectionMethodsTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createDetectionMethodsTable()

	assert.Equal(t, "create_detection_methods_table", migration.Name)
	assert.Equal(t, "Creates the detection_methods table", migration.Description)
	assert.Equal(t, "detection_methods", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Expect the SQL execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS detection_methods").
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Test the SQL execution
	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestCreateSessionsTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createSessionsTable()

	assert.Equal(t, "create_sessions_table", migration.Name)
	assert.Equal(t, "Creates the sessions table", migration.Description)
	assert.Equal(t, "sessions", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Expect the SQL execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS sessions").
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Test the SQL execution
	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestCreateAPIKeysTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createAPIKeysTable()

	assert.Equal(t, "create_api_keys_table", migration.Name)
	assert.Equal(t, "Creates the api_keys table", migration.Description)
	assert.Equal(t, "api_keys", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Expect the SQL execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS api_keys").
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Test the SQL execution
	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestCreateBanListTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createBanListTable()

	assert.Equal(t, "create_ban_lists_table", migration.Name)
	assert.Equal(t, "Creates the ban_lists table", migration.Description)
	assert.Equal(t, "ban_lists", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Expect the SQL execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS ban_lists").
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Test the SQL execution
	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}

func TestCreateBanListWordsTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createBanListWordsTable()

	assert.Equal(t, "create_ban_list_words_table", migration.Name)
	assert.Equal(t, "Creates the ban_list_words table", migration.Description)
	assert.Equal(t, "ban_list_words", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Expect the SQL execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS ban_list_words").
		WillReturnResult(sqlmock.NewResult(0, 0))

	// Test the SQL execution
	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())
}
