// Package constants provides shared constant values used throughout the application.
//
// The database_const.go file defines constants related to database structures,
// including table names, column names, and schema references. These constants
// ensure consistent and correct database access patterns throughout the application,
// reducing the risk of SQL errors and simplifying database schema changes.
package constants

// Table Names define the names of database tables used in the application.
// Using these constants instead of string literals ensures consistency
// and makes database schema changes easier to implement.
const (
	// TableUsers is the name of the table storing user account information.
	TableUsers = "users"

	// TableUserSettings is the name of the table storing user preferences and settings.
	TableUserSettings = "user_settings"

	// TableDocuments is the name of the table storing document metadata.
	TableDocuments = "documents"

	// TableDetectionMethods is the name of the table storing detection method configurations.
	TableDetectionMethods = "detection_methods"

	// TableDetectedEntities is the name of the table storing entities detected in documents.
	TableDetectedEntities = "detected_entities"

	// TableModelEntities is the name of the table storing entity definitions for detection models.
	TableModelEntities = "model_entities"

	// TableSearchPatterns is the name of the table storing search pattern definitions.
	TableSearchPatterns = "search_patterns"

	// TableBanLists is the name of the table storing ban list metadata.
	TableBanLists = "ban_lists"

	// TableBanListWords is the name of the table storing words included in ban lists.
	TableBanListWords = "ban_list_words"

	// TableSessions is the name of the table storing user session information.
	TableSessions = "sessions"

	// TableAPIKeys is the name of the table storing API key information.
	TableAPIKeys = "api_keys"
)

// Common Column Names define frequently used database column names.
// These constants ensure consistent column name usage in SQL queries.
const (
	// ColumnID is the generic primary key column name.
	ColumnID = "id"

	// ColumnUserID is the column name for user identifier foreign keys.
	ColumnUserID = "user_id"

	// ColumnSettingID is the column name for user setting identifier foreign keys.
	ColumnSettingID = "setting_id"

	// ColumnBanID is the column name for ban list identifier foreign keys.
	ColumnBanID = "ban_id"

	// ColumnMethodID is the column name for detection method identifier foreign keys.
	ColumnMethodID = "method_id"

	// ColumnEntityID is the column name for entity identifier foreign keys.
	ColumnEntityID = "entity_id"

	// ColumnPatternID is the column name for pattern identifier foreign keys.
	ColumnPatternID = "pattern_id"

	// ColumnCreatedAt is the column name for creation timestamps.
	ColumnCreatedAt = "created_at"

	// ColumnUsername is the column name for user usernames.
	ColumnUsername = "username"

	// ColumnPasswordHash is the column name for hashed passwords.
	ColumnPasswordHash = "password_hash"

	// ColumnSalt is the column name for password salt values.
	ColumnSalt = "salt"

	// ColumnKeyID is the column name for API key identifiers.
	ColumnKeyID = "key_id"

	// ColumnAPIKeyHash is the column name for hashed API key values.
	ColumnAPIKeyHash = "api_key_hash"

	// ColumnName is the column name for resource names.
	ColumnName = "name"

	// ColumnExpiresAt is the column name for expiration timestamps.
	ColumnExpiresAt = "expires_at"

	// ColumnWord is the column name for ban list words.
	ColumnWord = "word"

	// ColumnPatternType is the column name for search pattern types.
	ColumnPatternType = "pattern_type"

	// ColumnSessionID is the column name for session identifiers.
	ColumnSessionID = "session_id"

	// ColumnJWTID is the column name for JWT identifiers.
	ColumnJWTID = "jwt_id"

	// ColumnDocumentID is the column name for document identifiers.
	ColumnDocumentID = "document_id"

	// ColumnEntityName is the column name for entity names.
	ColumnEntityName = "entity_name"

	// ColumnMethodName is the column name for detection method names.
	ColumnMethodName = "method_name"

	// ColumnHighlightColor is the column name for entity highlighting colors.
	ColumnHighlightColor = "highlight_color"
)

// Index Names define database index names.
// These constants are used when creating or referencing database indexes.
const (
	// IndexJWTID is the name of the index on JWT identifiers.
	IndexJWTID = "idx_jwt_id"
)

// Database Schema Names define the names of database schemas.
// These constants are used when querying database metadata.
const (
	// SchemaInformation is the name of the PostgreSQL information schema.
	SchemaInformation = "information_schema"
)

// PostgreSQL SSL connection string parameters
const (
	PostgresSSLParams  = "sslmode=verify-ca sslrootcert=internal/database/certs/server-ca.pem sslcert=internal/database/certs/client-cert.pem sslkey=internal/database/certs/client-key.pem connect_timeout=15"
	PostgresSSLDisable = "sslmode=disable connect_timeout=15"
)
