package migrations

import (
	"context"
	"database/sql"
	"errors"
	"testing"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/stretchr/testify/assert"
)

// createMockDBAndTx creates a mock database and transaction for testing
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

// TestCreateUsersTable tests the createUsersTable function
func TestCreateUsersTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createUsersTable()

	assert.Equal(t, "create_users_table", migration.Name)
	assert.Equal(t, "Creates the users table", migration.Description)
	assert.Equal(t, "users", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Test successful execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS users").
		WillReturnResult(sqlmock.NewResult(0, 0))

	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())

	// Test execution failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS users").
		WillReturnError(errors.New("database error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)
}

// TestCreateUserSettingsTable tests the createUserSettingsTable function
func TestCreateUserSettingsTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createUserSettingsTable()

	assert.Equal(t, "create_user_settings_table", migration.Name)
	assert.Equal(t, "Creates the user_settings table", migration.Description)
	assert.Equal(t, "user_settings", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Test successful execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS user_settings").
		WillReturnResult(sqlmock.NewResult(0, 0))

	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())

	// Test execution failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS user_settings").
		WillReturnError(errors.New("database error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)
}

// TestCreateDocumentsTable tests the createDocumentsTable function
func TestCreateDocumentsTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createDocumentsTable()

	assert.Equal(t, "create_documents_table", migration.Name)
	assert.Equal(t, "Creates the documents table", migration.Description)
	assert.Equal(t, "documents", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Test successful execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS documents").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_user_id ON documents").
		WillReturnResult(sqlmock.NewResult(0, 0))

	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())

	// Test table creation failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS documents").
		WillReturnError(errors.New("table creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)

	// Test index creation failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS documents").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_user_id ON documents").
		WillReturnError(errors.New("index creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)
}

// TestCreateSearchPatternsTable tests the createSearchPatternsTable function
func TestCreateSearchPatternsTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createSearchPatternsTable()

	assert.Equal(t, "create_search_patterns_table", migration.Name)
	assert.Equal(t, "Creates the search_patterns table", migration.Description)
	assert.Equal(t, "search_patterns", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Test successful execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS search_patterns").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_setting_id ON search_patterns").
		WillReturnResult(sqlmock.NewResult(0, 0))

	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())

	// Test table creation failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS search_patterns").
		WillReturnError(errors.New("table creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)

	// Test index creation failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS search_patterns").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_setting_id ON search_patterns").
		WillReturnError(errors.New("index creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)
}

// TestCreateDetectionMethodsTable tests the createDetectionMethodsTable function
func TestCreateDetectionMethodsTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createDetectionMethodsTable()

	assert.Equal(t, "create_detection_methods_table", migration.Name)
	assert.Equal(t, "Creates the detection_methods table", migration.Description)
	assert.Equal(t, "detection_methods", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Test successful execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS detection_methods").
		WillReturnResult(sqlmock.NewResult(0, 0))

	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())

	// Test execution failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS detection_methods").
		WillReturnError(errors.New("database error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)
}

// TestCreateDetectedEntitiesTable tests the createDetectedEntitiesTable function
func TestCreateDetectedEntitiesTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createDetectedEntitiesTable()

	assert.Equal(t, "create_detected_entities_table", migration.Name)
	assert.Equal(t, "Creates the detected_entities table", migration.Description)
	assert.Equal(t, "detected_entities", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Test successful execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS detected_entities").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_document_id ON detected_entities").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_method_id ON detected_entities").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_entity_name ON detected_entities").
		WillReturnResult(sqlmock.NewResult(0, 0))

	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())

	// Test table creation failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS detected_entities").
		WillReturnError(errors.New("table creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)

	// Test index creation failures
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS detected_entities").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_document_id ON detected_entities").
		WillReturnError(errors.New("index creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)
}

// TestCreateModelEntitiesTable tests the createModelEntitiesTable function
func TestCreateModelEntitiesTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createModelEntitiesTable()

	assert.Equal(t, "create_model_entities_table", migration.Name)
	assert.Equal(t, "Creates the model_entities table", migration.Description)
	assert.Equal(t, "model_entities", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Test successful execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS model_entities").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_setting_id ON model_entities").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_method_id ON model_entities").
		WillReturnResult(sqlmock.NewResult(0, 0))

	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())

	// Test table creation failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS model_entities").
		WillReturnError(errors.New("table creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)

	// Test index creation failures
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS model_entities").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_setting_id ON model_entities").
		WillReturnError(errors.New("index creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)
}

// TestCreateBanListTable tests the createBanListTable function
func TestCreateBanListTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createBanListTable()

	assert.Equal(t, "create_ban_lists_table", migration.Name)
	assert.Equal(t, "Creates the ban_lists table", migration.Description)
	assert.Equal(t, "ban_lists", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Test successful execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS ban_lists").
		WillReturnResult(sqlmock.NewResult(0, 0))

	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())

	// Test execution failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS ban_lists").
		WillReturnError(errors.New("database error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)
}

// TestCreateBanListWordsTable tests the createBanListWordsTable function
func TestCreateBanListWordsTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createBanListWordsTable()

	assert.Equal(t, "create_ban_list_words_table", migration.Name)
	assert.Equal(t, "Creates the ban_list_words table", migration.Description)
	assert.Equal(t, "ban_list_words", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Test successful execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS ban_list_words").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_ban_id ON ban_list_words").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_word ON ban_list_words").
		WillReturnResult(sqlmock.NewResult(0, 0))

	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())

	// Test table creation failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS ban_list_words").
		WillReturnError(errors.New("table creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)

	// Test index creation failures
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS ban_list_words").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_ban_id ON ban_list_words").
		WillReturnError(errors.New("index creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)
}

// TestCreateSessionsTable tests the createSessionsTable function
func TestCreateSessionsTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createSessionsTable()

	assert.Equal(t, "create_sessions_table", migration.Name)
	assert.Equal(t, "Creates the sessions table", migration.Description)
	assert.Equal(t, "sessions", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Test successful execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS sessions").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_user_id ON sessions").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_jwt_id ON sessions").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_expires_at ON sessions").
		WillReturnResult(sqlmock.NewResult(0, 0))

	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())

	// Test table creation failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS sessions").
		WillReturnError(errors.New("table creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)

	// Test index creation failures
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS sessions").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_user_id ON sessions").
		WillReturnError(errors.New("index creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)
}

// TestCreateAPIKeysTable tests the createAPIKeysTable function
func TestCreateAPIKeysTable(t *testing.T) {
	_, tx, mock, cleanup := createMockDBAndTx(t)
	defer cleanup()

	migration := createAPIKeysTable()

	assert.Equal(t, "create_api_keys_table", migration.Name)
	assert.Equal(t, "Creates the api_keys table", migration.Description)
	assert.Equal(t, "api_keys", migration.TableName)
	assert.NotNil(t, migration.RunSQL)

	// Test successful execution
	mock.ExpectExec("CREATE TABLE IF NOT EXISTS api_keys").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_user_id ON api_keys").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_expires_at ON api_keys").
		WillReturnResult(sqlmock.NewResult(0, 0))

	ctx := context.Background()
	err := migration.RunSQL(ctx, tx)

	assert.NoError(t, err)
	assert.NoError(t, mock.ExpectationsWereMet())

	// Test table creation failure
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS api_keys").
		WillReturnError(errors.New("table creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)

	// Test index creation failures
	_, tx, mock, cleanup = createMockDBAndTx(t)
	defer cleanup()

	mock.ExpectExec("CREATE TABLE IF NOT EXISTS api_keys").
		WillReturnResult(sqlmock.NewResult(0, 0))
	mock.ExpectExec("CREATE INDEX IF NOT EXISTS idx_user_id ON api_keys").
		WillReturnError(errors.New("index creation error"))

	err = migration.RunSQL(ctx, tx)
	assert.Error(t, err)
}
